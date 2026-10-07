# Conecta Proteção

Projeto com uma interface web estática e um backend Python preparado para execução
local e desenvolvimento futuro.

## Recursos

- Conteúdos de orientação e proteção para crianças, adolescentes, familiares e educadores.
- Biblioteca Conecta com navegação acessível e responsiva.
- VLibras Widget oficial, carregado do domínio `vlibras.gov.br`.
- Interface de conversa do Assistente Conecta.

## Arquivos do projeto

- `index.html`: site, estilos e interações da interface.
- `server.py`: servidor local e integração do chatbot com a API da OpenAI.
- `database.py`: inicialização local do esquema SQLite preparado para contas e permissões.
- `.env.example`: modelo das variáveis de ambiente; não contém uma chave válida.
- `.gitignore`: exclui credenciais, banco local e arquivos temporários do Git.

## Executar localmente

Requer Python 3.10 ou superior. O servidor utiliza somente a biblioteca padrão do
Python.

1. Copie `.env.example` para `.env` e configure `OPENAI_API_KEY` com sua chave da API
   OpenAI. A chave fica somente no servidor; nunca a coloque no HTML/JavaScript nem
   envie o arquivo `.env` ao GitHub.
2. Inicie o servidor na pasta do projeto:

   ```powershell
   python server.py
   ```

3. Abra o endereço HTTP mostrado pelo servidor, normalmente
   `http://127.0.0.1:8765`. Não abra `index.html` diretamente por `file://` nem sirva a
   pasta com `python -m http.server`: esses modos não atendem `/api/chat`.

4. No chatbot, escolha **Criar conta**. O cadastro solicita somente nome de usuário e
   senha; não há campo de e-mail nem cadastro externo. O nome deve ter de 3 a 24
   caracteres, usar letras/números/ponto/hífen/sublinhado e não conter termos ofensivos.
   A senha precisa ter pelo menos 12 caracteres.

Contas também podem ser provisionadas localmente pelo administrador com
`python server.py create-user`; o terminal solicita nome de usuário, perfil e senha
sem exibir o valor digitado.

Se a porta 8765 já estiver ocupada, escolha outra e mantenha esse servidor em
execução, por exemplo:

```powershell
$env:PORT = "8766"
python server.py
```

Nesse caso, abra `http://127.0.0.1:8766`.

O servidor cria `.private/conecta_protecao.sqlite3` para contas e sessões. Senhas são
armazenadas com PBKDF2; cookies de sessão são `HttpOnly`, `SameSite=Strict` e expiram
após oito horas. Somente sessões válidas podem acessar `/api/chat`. Em produção,
publique o backend apenas por HTTPS e configure `SESSION_COOKIE_SECURE=1`.

## Limites da publicação no GitHub Pages

O GitHub Pages publica arquivos estáticos; ele não executa o servidor Python nem o
banco SQLite do projeto. Por isso, o chatbot autenticado não recebe respostas de IA
quando o site é aberto pelo GitHub Pages. Para usar o chatbot, publique o backend
separadamente em HTTPS e configure a comunicação do frontend com esse serviço.

Não coloque chaves de API, arquivos `.env`, bancos de dados, cadastros ou dados de
conversa neste repositório público.

## VLibras

O widget oficial do VLibras é integrado em `index.html`. Sua disponibilidade e a tradução dos conteúdos dependem dos serviços externos oficiais e de conexão com a internet.