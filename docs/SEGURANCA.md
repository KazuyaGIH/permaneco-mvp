# Segurança

## M1 — verificações

- Sessões usam tokens aleatórios com hash no banco, expiração e cookies `HttpOnly`, `SameSite=Lax` e `Secure` por padrão. Para HTTP local, `COOKIE_SECURE=false` é uma opção exclusiva de desenvolvimento.
- Requisições autenticadas que alteram estado exigem CSRF double-submit.
- As rotas de tutor e administração derivam a identidade da sessão, limitam escopo no backend e registram acessos no log append-only.
- Conteúdo livre é cifrado com AES-GCM; as chaves são fornecidas pelo ambiente e identificadas para permitir rotação.
- O Caddy define CSP sem recursos externos de imagem ou script, `frame-ancestors 'none'`, `X-Content-Type-Options` e `Referrer-Policy`.

### Verificação manual de cabeçalhos

Com o Compose iniciado, execute `curl -sSI http://localhost:8080/` e confirme os cabeçalhos `Content-Security-Policy`, `X-Content-Type-Options: nosniff` e `Referrer-Policy`. A CSP deve conter `frame-ancestors 'none'` e não permitir scripts ou imagens externos.

## Antes de usar dados reais

Dados reais exigem revisão jurídica e de privacidade, base legal definida com a instituição, avaliação de transferência internacional, RIPD, contrato de tratamento de dados e protocolo de crise revisado por profissionais. O provedor de IA deve oferecer termos que proíbam treinamento com os dados. O MVP não está aprovado para dados reais.
