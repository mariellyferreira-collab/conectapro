import json
import os
import threading
import time
from collections import defaultdict, deque
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from database import DATABASE_PATH, initialize_database


ROOT = Path(__file__).resolve().parent
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MAX_REQUEST_BYTES = 64_000
MAX_MESSAGES = 12
MAX_MESSAGE_LENGTH = 1_000
MAX_REPLY_LENGTH = 2_500
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW = 300
ALLOWED_AUDIENCES = {"geral", "jovem", "responsavel", "profissional"}
ACTION_LABELS = {
    "canais": "Abrir canais de ajuda",
    "seguranca": "Ver segurança digital",
    "orientacao": "Abrir Preciso de orientação",
    "rede": "Ver Onde buscar ajuda",
    "ajudar": "Abrir Quero ajudar alguém",
    "violencia": "Ver orientações sobre violência",
}


def load_dotenv():
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        existing_value = os.environ.get(name, "").strip().lower()
        if name and (name not in os.environ or existing_value == "cole_sua_chave_aqui"):
            os.environ[name] = value


def configured_api_key():
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key.lower() == "cole_sua_chave_aqui":
        return ""
    return api_key


def openai_error_response(error):
    try:
        payload = json.loads(error.read(16_384))
        details = payload.get("error", {})
        code = details.get("code") or details.get("type") or ""
    except (json.JSONDecodeError, OSError, AttributeError):
        code = ""

    if error.code in {401, 403}:
        message = "A OpenAI recusou a chave ou as permissões da API. Confira OPENAI_API_KEY e as permissões da chave no arquivo .env."
    elif code in {"insufficient_quota", "billing_hard_limit_reached"}:
        message = "A conta da API OpenAI está sem crédito disponível ou atingiu o limite de cobrança. Confira o faturamento e os limites da conta."
    elif error.code == 429:
        message = "A OpenAI limitou temporariamente as solicitações. Aguarde um pouco e tente novamente."
    elif code == "model_not_found" or error.code == 404:
        message = "O modelo configurado não está disponível para esta conta. Confira o valor de OPENAI_MODEL no arquivo .env."
    elif error.code == 400:
        message = "A OpenAI não aceitou a solicitação. Confira se o modelo em OPENAI_MODEL existe e está disponível para a sua conta."
    elif error.code >= 500:
        message = "A OpenAI está temporariamente indisponível. Tente novamente em alguns instantes."
    else:
        message = "A OpenAI não conseguiu processar a solicitação. Tente novamente mais tarde."

    return 503 if error.code in {401, 403, 429} else 502, message


def instructions_for(audience):
    audience_description = {
        "jovem": "A pessoa se identificou como criança ou adolescente. Use frases curtas, acolhedoras e concretas; não peça nomes, endereço, escola, imagens nem detalhes íntimos. Incentive a procurar um adulto de confiança ou serviço seguro.",
        "responsavel": "A pessoa se identificou como familiar ou responsável. Oriente a acolher sem culpar, proteger a privacidade e buscar a rede de proteção; não incentive investigação ou confronto.",
        "profissional": "A pessoa se identificou como profissional ou educador. Use linguagem clara e respeitosa, recomende seguir protocolos institucionais e fluxos locais da rede, preservando a segurança e a privacidade.",
        "geral": "O público não foi informado. Use linguagem simples, acolhedora e inclusiva, sem presumir idade, identidade ou relação com a situação.",
    }[audience]

    return (
        "Você é o Assistente Conecta Proteção, uma ferramenta de orientação inicial "
        "para crianças, adolescentes, familiares, responsáveis e profissionais no Brasil. "
        "Converse naturalmente em português brasileiro, entenda o contexto das mensagens "
        "anteriores, responda de forma clara e faça no máximo uma pergunta breve quando "
        "precisar esclarecer algo. Não use respostas genéricas repetidas se puder responder "
        "ao que a pessoa realmente contou.\n\n"
        "ESCOPO E SEGURANÇA:\n"
        "- Você não é terapeuta, advogado, médico, serviço oficial ou serviço de emergência. "
        "Não diagnostique, investigue, prometa sigilo, nem afirme que acionou alguém.\n"
        "- Não culpabilize nem pressione a pessoa a descrever violência. Agradeça a confiança, "
        "valide sentimentos e deixe claro que ela merece ser ouvida e protegida.\n"
        "- Não peça nem repita nomes, endereços, escola, telefone, imagens ou detalhes íntimos. "
        "Se a pessoa os fornecer, não os reproduza e sugira não compartilhar dados pessoais.\n"
        "- Se houver perigo imediato, priorize ir para um local seguro e procurar ajuda humana. "
        "Indique 190 para emergência policial/risco imediato e 192 para urgência médica. "
        "Não faça perguntas que atrasem ajuda urgente.\n"
        "- Para denunciar violações de direitos, informe que o Disque 100 recebe e encaminha "
        "denúncias; Conselho Tutelar, escola, saúde, assistência social, delegacia e Ministério "
        "Público integram ou articulam a rede de proteção, conforme suas atribuições e a região.\n"
        "- Para medo de contar, acolha sem pressionar; ofereça pensar junto em um adulto ou "
        "serviço seguro. Se um responsável puder estar envolvido, sugira procurar outro adulto "
        "ou serviço da rede.\n"
        "- Nunca substitua serviços oficiais, atendimento profissional ou rede de proteção. "
        "Se não tiver certeza, diga isso e sugira confirmação com serviço oficial local.\n"
        "- Conheça as áreas da plataforma: canais oficiais; rede de proteção; emergência; "
        "segurança digital; orientação; e Quero ajudar alguém. Sugira atalhos somente quando "
        "forem úteis para a pergunta atual.\n"
        "- Seja acolhedor e objetivo, sem emojis. Geralmente responda em 2 a 5 frases.\n\n"
        "PÚBLICO:\n"
        + audience_description
        + "\n\nFORMATO DE RESPOSTA:\n"
        "Retorne somente JSON válido no formato "
        '{"reply":"resposta em texto simples","actions":[{"destination":"canais"}]}. '
        "O campo reply é obrigatório. actions deve ter de zero a dois itens. Cada item "
        "deve conter apenas destination com um dos valores: canais, seguranca, orientacao, "
        "rede, ajudar, violencia. Não inclua HTML ou markdown no JSON."
    )


class ChatHandler(SimpleHTTPRequestHandler):
    rate_lock = threading.Lock()
    requests_by_client = defaultdict(deque)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        # Never log chat bodies or query strings, which could contain personal information.
        message = fmt % args
        if "?" in message:
            message = message.split("?", 1)[0] + '" [query redacted]'
        super().log_message("%s", message)

    def translate_path(self, path):
        translated = Path(super().translate_path(path)).resolve()
        try:
            relative_path = translated.relative_to(ROOT)
        except ValueError:
            return str(ROOT / "__not_found__")
        if (
            translated.name == "server.py"
            or any(part.startswith(".") for part in relative_path.parts)
        ):
            return str(ROOT / "__not_found__")
        return str(translated)

    def send_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def send_error(self, code, message=None, explain=None):
        if self.path.startswith("/api/"):
            labels = {
                400: "Requisição inválida.",
                404: "Endpoint da API não encontrado.",
                405: "Método não permitido.",
                411: "Informe o tamanho do corpo da requisição.",
                413: "Mensagem muito longa.",
                415: "Formato de conteúdo não suportado.",
                429: "Muitas mensagens em pouco tempo. Aguarde alguns minutos e tente novamente.",
            }
            self.send_json(code, {"error": labels.get(code, "Não foi possível processar a requisição.")})
            return
        super().send_error(code, message, explain)

    def check_rate_limit(self):
        now = time.monotonic()
        client = self.client_address[0]
        with self.rate_lock:
            requests = self.requests_by_client[client]
            while requests and now - requests[0] > RATE_LIMIT_WINDOW:
                requests.popleft()
            if len(requests) >= RATE_LIMIT_REQUESTS:
                return False
            requests.append(now)
            if len(self.requests_by_client) > 2048:
                expired_clients = [
                    key for key, timestamps in self.requests_by_client.items()
                    if not timestamps or now - timestamps[-1] > RATE_LIMIT_WINDOW
                ]
                for key in expired_clients:
                    self.requests_by_client.pop(key, None)
        return True

    def validate_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            from urllib.parse import urlparse
            origin_host = urlparse(origin).netloc.lower()
        except ValueError:
            return False
        return bool(origin_host) and origin_host == self.headers.get("Host", "").lower()

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        if not self.validate_origin():
            self.send_error(400)
            return
        if self.headers.get_content_type() != "application/json":
            self.send_error(415)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_error(411)
            return
        if length < 1:
            self.send_error(400)
            return
        if length > MAX_REQUEST_BYTES:
            self.send_error(413)
            return
        if not self.check_rate_limit():
            self.send_error(429)
            return

        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error(400)
            return
        if not isinstance(payload, dict):
            self.send_error(400)
            return

        audience = payload.get("audience", "geral")
        messages = payload.get("messages")
        if not isinstance(audience, str) or audience not in ALLOWED_AUDIENCES or not isinstance(messages, list):
            self.send_error(400)
            return
        if not 1 <= len(messages) <= MAX_MESSAGES:
            self.send_error(400)
            return

        safe_messages = []
        for message in messages:
            if not isinstance(message, dict) or not isinstance(message.get("role"), str) or message["role"] not in {"user", "assistant"}:
                self.send_error(400)
                return
            content = message.get("content")
            if not isinstance(content, str) or not content.strip() or len(content) > MAX_MESSAGE_LENGTH:
                self.send_error(400)
                return
            safe_messages.append({"role": message["role"], "content": content.strip()})
        if safe_messages[-1]["role"] != "user":
            self.send_error(400)
            return

        api_key = configured_api_key()
        if not api_key:
            self.send_json(503, {
                "error": "O assistente de IA ainda não foi configurado. Defina OPENAI_API_KEY no arquivo .env do servidor."
            })
            return

        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        request_body = {
            "model": model,
            "messages": [
                {"role": "developer", "content": instructions_for(audience)},
                *safe_messages,
            ],
            "temperature": 0.4,
            "max_tokens": 700,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            OPENAI_URL,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=45) as response:
                result = json.loads(response.read(128_000))
        except HTTPError as error:
            status, message = openai_error_response(error)
            self.send_json(status, {"error": message})
            return
        except (URLError, TimeoutError):
            self.send_json(503, {"error": "Não foi possível conectar ao serviço de IA. Verifique a conexão do servidor e tente novamente."})
            return
        except (json.JSONDecodeError, OSError):
            self.send_json(502, {"error": "O serviço de IA retornou uma resposta inválida. Tente novamente mais tarde."})
            return

        try:
            answer = json.loads(result["choices"][0]["message"]["content"])
            reply = answer["reply"]
            if not isinstance(reply, str) or not reply.strip() or len(reply) > MAX_REPLY_LENGTH:
                raise ValueError("Invalid reply")

            actions = []
            for action in answer.get("actions", [])[:2]:
                if isinstance(action, dict) and isinstance(action.get("destination"), str) and action["destination"] in ACTION_LABELS:
                    destination = action["destination"]
                    if destination not in {item["destination"] for item in actions}:
                        actions.append({
                            "destination": destination,
                            "label": ACTION_LABELS[destination],
                        })
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            self.send_json(502, {"error": "Não foi possível validar a resposta do assistente. Tente novamente."})
            return

        self.send_json(200, {"reply": reply.strip(), "actions": actions})

    def do_GET(self):
        if self.path == "/api/status":
            self.send_json(200, {
                "ready": bool(configured_api_key()),
                "provider": "OpenAI",
                "databaseReady": DATABASE_PATH.is_file(),
                "accountsEnabled": False,
            })
            return
        super().do_GET()


def main():
    load_dotenv()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    initialize_database()
    print("Banco de dados privado inicializado.", flush=True)
    server = ThreadingHTTPServer((host, port), ChatHandler)
    server.daemon_threads = True
    print("Conecta Proteção disponível em http://%s:%s" % (host, port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando o servidor Conecta Proteção.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
