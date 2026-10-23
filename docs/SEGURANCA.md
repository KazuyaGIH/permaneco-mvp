# Segurança

## M1 — verificações

- Sessões usam tokens aleatórios com hash no banco, expiração e cookies `HttpOnly`, `SameSite=Lax` e `Secure` por padrão. Para HTTP local, `COOKIE_SECURE=false` é uma opção exclusiva de desenvolvimento.
- Requisições autenticadas que alteram estado exigem CSRF double-submit.
- As rotas de tutor e administração derivam a identidade da sessão, limitam escopo no backend e registram acessos no log append-only.
- Conteúdo livre é cifrado com AES-GCM; as chaves são fornecidas pelo ambiente e identificadas para permitir rotação.
- O Caddy define CSP sem recursos externos de imagem ou script, `frame-ancestors 'none'`, `X-Content-Type-Options` e `Referrer-Policy`.

## M2 — controles e testes

- **Redação e limpeza Unicode:** `backend/app/security/sanitize.py` normaliza NFKC, remove controles e oculta identificadores pessoais. Cobertura: `test_redacts_personal_data`, `test_card_redaction_requires_luhn` e `test_unicode_normalization_and_control_removal` em `backend/tests/test_ai_core.py`.
- **Escape de delimitadores:** `backend/app/ai/context.py`, `background.py` e `plans.py` escapam tags nas mensagens, memórias, perfil, conhecimento e mudanças solicitadas. Cobertura: `test_context_tag_imitations_are_escaped`, `test_student_message_cannot_close_conversation_block`, `test_background_prompts_escape_transcript_and_existing_memories` e `test_plan_prompt_escapes_requested_change_and_includes_local_timezone`.
- **Canário:** `backend/app/ai/pipeline.py` segura o sufixo do streaming e substitui respostas que contenham o canário. Cobertura: `test_pipeline_canary_split_across_chunks_never_leaks`.
- **Allowlist de links:** `backend/app/ai/pipeline.py` mantém somente domínios permitidos e seus subdomínios, removendo HTML e imagens Markdown. Cobertura: `test_output_strips_markup_and_filters_links`.
- **Ferramentas fechadas e escopo da sessão:** `backend/app/ai/tools.py` valida argumentos por schemas estritos e recebe `student_id` exclusivamente da sessão; `pipeline.py` limita a três chamadas por turno. Cobertura: `test_tool_schemas_are_closed_and_never_accept_student_id`, `test_tools_use_the_server_student_id_and_reject_model_id` e `test_tool_calls_are_capped_at_three`.
- **Antienvenenamento de memória e consentimento:** `backend/app/ai/background.py` descarta instruções, conteúdo suspeito e dados pessoais; só extrai ou atualiza memórias com consentimento ativo. Cobertura: `test_memory_extraction_requires_consent_and_filters_candidates` e `test_memory_consent_can_be_revoked_without_extracting_more`.
- **Validação do plano:** `backend/app/ai/plans.py` verifica horas semanais e referências a itens ativos, exigindo que auxílios sejam do tipo `auxilio`. Cobertura: `test_plan_rejects_hours_over_free_time` e `test_plan_rejects_unknown_and_non_auxilio_knowledge`.
- **Falha segura do provedor:** `backend/app/ai/pipeline.py` preserva a mensagem do estudante e devolve erro amigável sem persistir resposta insegura. Cobertura: `test_pipeline_provider_failure_preserves_student_message`, `test_chat_provider_down_sends_error_and_keeps_user_message` e `test_fake_provider_down_mode_raises`.

### Verificação manual de cabeçalhos

Com o Compose iniciado, execute `curl -sSI http://localhost:8080/` e confirme os cabeçalhos `Content-Security-Policy`, `X-Content-Type-Options: nosniff` e `Referrer-Policy`. A CSP deve conter `frame-ancestors 'none'` e não permitir scripts ou imagens externos.

## Antes de usar dados reais

Dados reais exigem revisão jurídica e de privacidade, base legal definida com a instituição, avaliação de transferência internacional, RIPD, contrato de tratamento de dados e protocolo de crise revisado por profissionais. O provedor de IA deve oferecer termos que proíbam treinamento com os dados. O MVP não está aprovado para dados reais.
