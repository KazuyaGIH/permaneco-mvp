# Permaneço

MVP de acompanhamento acolhedor para estudantes de cursos EAD. O M1 usa somente dados sintéticos.

## Rodar localmente

1. Execute `make setup` para criar `.env` com uma chave aleatória local.
2. Execute `make up`.
3. Execute `make seed` e abra <http://localhost:8080>.

O Compose publica somente em `localhost`. O ambiente local usa HTTP para simplificar a demonstração. `COOKIE_SECURE=false` só deve ser usado nesse ambiente; ambientes externos devem usar TLS e `COOKIE_SECURE=true`.

## Contas de demonstração

As contas são criadas por `make seed`, somente quando `DEMO_MODE=true`. A senha é definida por `DEMO_PASSWORD` no arquivo `.env`; o valor de exemplo é deliberadamente conhecido e não deve ser reutilizado fora da demonstração.

- `ana@example.com` — estudante
- `bruno@example.com` — estudante
- `tutor1@example.com` — tutor
- `admin@example.com` — administração

## Roteiro do M1

Entre como Ana, confira seu perfil, depois acesse como tutor para consultar somente estudantes atribuídos. A conta administrativa lista apenas contas e papéis, sem conteúdo privado.

## Arquitetura

```mermaid
flowchart LR
    Browser --> Caddy
    Caddy -->|/api/*| FastAPI
    Caddy -->|demais rotas| Next
    FastAPI --> PostgreSQL
    Worker --> PostgreSQL
```

## Limitações

O M1 estabelece autenticação, autorização, persistência, criptografia e execução local. Chat, IA, cadência funcional, painel e fluxos de consentimento completos fazem parte de marcos posteriores. O rate limiting é em memória e não é compartilhado entre réplicas.

## Antes de usar dados reais

Use um provedor de IA em plano apropriado e com termos que proíbam treinamento com os dados; avalie transferência internacional conforme a LGPD; produza RIPD; defina a base legal com o encarregado de dados da instituição — consentimento pode não ser livre se o acompanhamento for obrigatório — e valide o protocolo de crise com profissionais de saúde mental e plantão humano. O M1 não deve receber dados reais.
