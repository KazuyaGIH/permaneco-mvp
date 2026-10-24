# Datathon Impacta.dev 2026 — Time BANANA DATE

**Tema:** desistência no ensino superior brasileiro. De 2020 a 2024, a taxa anual de desistência subiu de 17,1% para 22,6%, e quase toda essa piora (5,4 dos 5,5 p.p.) veio do EAD privado.

**Resposta do time:** a **Permaneço**, uma mentora de IA com memória que acompanha calouros do EAD privado no começo do curso, quando a maior parte da desistência acontece.

Time: Fernando Graminholi, Gustavo Hassui, Murilo Maeda e Tamara Maia.

## O que tem neste repositório

| Pasta | Conteúdo |
|---|---|
| [`datathon/`](datathon/) | A análise de dados: notebook com todas as contas, apresentação em PDF e as colas de perguntas para a banca |
| [`permaneco/`](permaneco/) | O app da Permaneço (MVP funcional): backend, frontend, Docker e documentação técnica |
| [`permaneco/docs/MANUAL.md`](permaneco/docs/MANUAL.md) | Manual de uso: como instalar, entrar e testar cada funcionalidade |

## O que os dados mostram

Resumo das cinco afirmações testadas no notebook (Censo da Educação Superior 2020–2024, dados por curso):

1. **O aluno está no EAD privado.** Em 2024, mais da metade dos vínculos eram do EAD privado, que também tem a maior desistência (28,9% em 2024).
2. **A desistência acontece no começo.** No EAD privado, 43% da turma já saiu até o fim do ano seguinte ao ingresso; 64% de toda a desistência de seis anos acontece nos dois primeiros.
3. **Não é só o tipo de faculdade.** Na mesma instituição, o EAD perde cerca de 7,8 p.p. a mais que o presencial.
4. **Quem é o aluno.** Adulto (74% têm 25 anos ou mais), vindo da escola pública, quase sem apoio financeiro (1% com apoio social).
5. **O risco é previsível e a escala pede IA.** A perda do primeiro ano não volta; acompanhar 3,26 milhões de calouros por 20 min/mês exigiria cerca de 9 mil tutores em tempo integral, e 54% desses alunos estão em cinco instituições.

A literatura aponta que o que funciona é acompanhamento ativo e regular (InsideTrack, CUNY ASAP); dinheiro sem acompanhamento e filtro duro no primeiro ano não funcionaram.

## A solução em uma frase

A Permaneço conversa com o calouro no horário dele, lembra da rotina e dos objetivos, monta um plano de estudos, carreira e finanças que cabe no tempo real do aluno e avisa um tutor humano quando o caso pede intervenção.

## Como testar rápido

1. Leia a apresentação: [`datathon/Permaneco-Estudo-e-Proposta.pdf`](datathon/Permaneco-Estudo-e-Proposta.pdf).
2. Abra o notebook no Colab: [`datathon/BANANA_DATE_Permanencia_EAD_analises.ipynb`](datathon/BANANA_DATE_Permanencia_EAD_analises.ipynb). Ele baixa os dados sozinho.
3. Rode o app seguindo o [manual](permaneco/docs/MANUAL.md). Precisa de Docker e de uma chave gratuita do Gemini.

## Stack do app

Next.js (TypeScript) no front, FastAPI (Python) no back, PostgreSQL com dados criptografados, IA pela API do Gemini (modelos gratuitos) e Docker Compose para subir tudo. Detalhes em [`permaneco/README.md`](permaneco/README.md) e [`permaneco/docs/`](permaneco/docs/).
