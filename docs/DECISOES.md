# Decisões técnicas

- As sessões são mantidas na tabela `sessions`; o cookie contém apenas um token aleatório, cujo hash é armazenado no banco.
- CSRF usa double-submit: `csrf_token` é legível por JavaScript e toda requisição autenticada que altera estado envia o mesmo valor em `X-CSRF-Token`. Login é a única exceção.
- O rate limiting do MVP é mantido em memória por processo e deve ser substituído por armazenamento compartilhado antes de escalar horizontalmente.
- O relógio de demonstração persiste seu deslocamento na tabela `demo_clock` e só é ativado quando `DEMO_MODE=true`.
- SQLAlchemy é síncrono; as rotas usam sessões curtas e PostgreSQL.
- O frontend e as APIs compartilham origem pelo Caddy; a execução local usa HTTP somente em `localhost:8080`. Em ambientes externos, TLS deve ser obrigatório.
- A listagem administrativa mostra somente contas e papéis, sem dados de conversas, memórias ou planos.
- O primeiro migration cria o esquema definido pelos modelos e instala a proteção de imutabilidade do log de auditoria no PostgreSQL.
- Não existe integração com provedores de IA no M1; o worker apenas registra batimentos sem informações pessoais ou conteúdo.
