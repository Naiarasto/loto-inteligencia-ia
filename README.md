# Loto Inteligência IA — versão inicial

Este é o primeiro MVP do sistema. Ele roda como um aplicativo Streamlit e pode ser publicado na internet pelo Streamlit Community Cloud.

## O que já funciona
- Painel para Lotofácil e Mega-Sena.
- Importação de histórico em CSV.
- Validação básica das dezenas.
- Frequência histórica por dezena.
- Ranking das mais e menos frequentes.
- Geração de 10 combinações únicas por modalidade.
- Dois modos: equilibrado (ponderação histórica muito leve) e aleatório.
- Exportação dos jogos em CSV.
- Exibição da probabilidade matemática da aposta simples.

## O que ainda não está conectado
- Atualização automática dos resultados oficiais da Caixa.
- Testes retrospectivos (backtesting) com comparação estatística.
- Banco de dados persistente de concursos e jogos.
- Login e painel multiusuário.

Não considere a frequência passada uma previsão. Em sorteios justos e independentes, cada combinação simples tem a mesma probabilidade em cada concurso.

## Como executar no computador
1. Instale Python 3.10 ou superior.
2. Extraia o ZIP.
3. Abra o terminal na pasta do projeto.
4. Execute:
   ```bash
   pip install -r requirements.txt
   streamlit run app.py
   ```
5. O navegador abrirá o painel.

## Como publicar na internet (sem pagar inicialmente)
1. Crie uma conta no GitHub.
2. Crie um repositório novo e envie `app.py` e `requirements.txt`.
3. Entre em https://share.streamlit.io/ e conecte seu GitHub.
4. Escolha o repositório e o arquivo principal `app.py`.
5. Clique em Deploy.

A publicação gratuita depende dos limites e termos vigentes do provedor. Não coloque senhas ou dados pessoais no repositório.

## Formato do CSV
O arquivo deve conter uma linha por concurso. As colunas obrigatórias são:
- `concurso`
- `data`
- `bola1`, `bola2`, ... até `bola15` para Lotofácil
- `bola1`, `bola2`, ... até `bola6` para Mega-Sena

Exemplo apenas de estrutura (números fictícios, não são resultados reais):
```csv
concurso,data,bola1,bola2,bola3,bola4,bola5,bola6
1,2000-01-01,1,2,3,4,5,6
```
O exemplo acima é apenas ilustrativo e não representa resultado oficial.
