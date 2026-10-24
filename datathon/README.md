# Análise do Datathon

Arquivos da parte analítica e da apresentação.

| Arquivo | O que é |
|---|---|
| `BANANA_DATE_Permanencia_EAD_analises.ipynb` | Notebook com todas as análises que sustentam a tese. Feito para o Google Colab. |
| `Permaneco-Estudo-e-Proposta.pdf` | Apresentação final: o que os dados revelam e a proposta da Permaneço. |
| `Permaneco-Solucao.pdf` | Resumo da solução: problema, funcionamento, features, segurança e roteiro de teste. |
| `Permaneco-Perguntas-Tecnicas.pdf` | Perguntas e respostas curtas sobre o app e a IA, para a banca. |

## Como rodar o notebook

1. Abra o `.ipynb` no [Google Colab](https://colab.research.google.com/) (Arquivo → Abrir notebook → GitHub, ou faça upload).
2. Execute as células em ordem. A primeira célula baixa os dados em parquet da pasta pública do time via `gdown`, então não precisa subir nada.
3. Só usa `pandas` e `matplotlib`, já instalados no Colab.

## Dados

Censo da Educação Superior (INEP) de 2020 a 2024, agregado por curso e ano. Três tabelas:

- `cursos_ano`: vínculos, ingressantes e desvinculados por curso e ano;
- `trajetoria_cursos` e `trajetoria_cursos_anual`: desistência acumulada das turmas de 2015 a 2020, ano a ano;
- `fluxo_inep_contexto`: evasão por faixa etária, do fluxo oficial do INEP.

Os dados são por curso, não por aluno. Toda taxa de grupo é soma ÷ soma, nunca a média das taxas dos cursos.

## Método

Análise exploratória, sem modelo preditivo: comparação de taxas por segmento (rede × modalidade), por ano e por anos desde o ingresso, com pares de cursos da mesma instituição para separar o efeito da modalidade. A seção 8 traz contas de ordem de grandeza (tutores necessários, alunos a mais por turma e tamanho de amostra de um piloto), com premissas editáveis.

## Estrutura do notebook

1. Ambiente e dados
2. Afirmação 1: EAD privado
3. Afirmação 2: começo do curso
4. Afirmação 3: tipo de faculdade
5. Afirmação 4: perfil do aluno
6. Afirmação 5a: risco previsível
7. Afirmação 5b: poucos parceiros
8. Por que IA e quanto vale
