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

## M2 — núcleo de IA

- Os modelos padrão são `gemini-3.6-flash` para conversas e planos e `gemini-3.5-flash-lite` para tarefas rápidas. Foram escolhidos por estarem disponíveis sem cobrança no nível gratuito validado, permitindo testar o MVP sem créditos pagos.
- A resposta em streaming libera apenas deltas já seguros e mantém um trecho final em espera para detectar um canário dividido entre chunks. Ao terminar, o texto completo passa pela sanitização e é enviado como `replace`, garantindo que o conteúdo persistido e o exibido coincidam.
- A base de conhecimento guarda texto simples com busca `tsvector` em português: seu conteúdo curado é público e não é dado pessoal. Conteúdo pessoal continua cifrado.
- O encerramento da conversa usa `BackgroundTasks` do FastAPI para resumo, próximos passos, extração consentida de memórias e geração do plano sem bloquear a resposta da rota.
- O limite diário é de 25 mil tokens por estudante e dia do relógio de demonstração. Foi elevado de 10 mil após uma geração de plano consumir mais de 10 mil tokens e impedir a conclusão do fluxo de conversa e do plano; o limite continua aplicado para conter uso excessivo.
