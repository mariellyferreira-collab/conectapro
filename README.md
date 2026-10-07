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

1. Copie `.env.example` para `.env` e configure `OPENAI_API_KEY` usando sua própria
   chave da API OpenAI. Nunca compartilhe nem envie essa chave ao GitHub.
2. Inicie o servidor na pasta do projeto:

   ```powershell
   python server.py
   ```

3. Acesse `http://127.0.0.1:8765`.

O servidor cria o banco local em `.private/conecta_protecao.sqlite3`. O banco,
credenciais e arquivos temporários são ignorados pelo Git e não fazem parte deste
repositório. A estrutura de contas e permissões é apenas uma preparação: cadastro,
login e sessões não estão ativados.

## Limites da publicação no GitHub Pages

O GitHub Pages publica arquivos estáticos; ele não executa o servidor Python nem o
banco SQLite do projeto. Por isso, nesta publicação estática, as solicitações à API de
chat não recebem respostas de IA. Os arquivos do backend estão guardados neste
repositório para trabalho futuro, mas não estão hospedados nem são executados pelo
GitHub Pages. O chatbot só poderá conversar com um modelo real quando um backend for
implantado separadamente e a comunicação entre o site e esse serviço for configurada
com HTTPS, validação de origem e credenciais mantidas exclusivamente no servidor.

Não coloque chaves de API, arquivos `.env`, bancos de dados, cadastros ou dados de
conversa neste repositório público. Nenhuma conta de usuário é exigida por esta versão.

## VLibras

O widget oficial do VLibras é integrado em `index.html`. Sua disponibilidade e a tradução dos conteúdos dependem dos serviços externos oficiais e de conexão com a internet.