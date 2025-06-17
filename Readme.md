# Portfólio NPI Backend

Este repositório reúne uma API desenvolvida em **Python 3.13** utilizando o framework **FastAPI**. O projeto demonstra práticas de construção de serviços REST, cache em Redis e autenticação básica, servindo como parte do meu portfólio profissional e para um projeto interno da empresa, servindo utilmente para o setor, integrado com o Pipefy.

## Tecnologias e ferramentas
- **FastAPI**
- **Uvicorn**
- **Redis**
- **Python-dotenv**

## Pipefy
Sistema de gerenciamento de processos.
#### Utilizado como
- Database (Coleta e armazenamento de dados)
- Controle do processo
- Meio de envio de e-mails automáticos de comunicação
#### Benefícios
- ETL simplicado pois sua api (graphql) possui um formato padrão independente do dado inserido.
- Fácil utilização
- Escalável
- Gerenciável

## Estrutura do projeto
O arquivo `api/main.py` concentra a aplicação e expõe rotas para:
- consulta e atualização de informações de cursos;
- gerenciamento de usuários e verificação de login;
- geração e validação de hashes de senha e códigos de acesso.

As funções específicas ficam em `api/utils` e os modelos em `api/models.py`, organizando a lógica de negócio de forma clara.

## Funcionalidades desenvolvidas

#### **Login API**
- **Registro de usuários**: Permite criar novos usuários com validação de dados.
- **Autenticação**: Implementa autenticação básica com validação de credenciais.
- **Geração de tokens**: Cria tokens de acesso para sessões autenticadas.
- **Validação de tokens**: Verifica a validade e expiração de tokens para proteger rotas privadas.
- **Recuperação de senha**: Gera códigos temporários para redefinição de senha.

#### **Courses API**
- **Listagem de cursos no Pipefy**: Retorna uma lista de cursos disponíveis com detalhes como título, descrição e duração.
É realizada uma consulta numa "phase" específica do pipefy, buscando todos os cards (Propostas) naquela fase.

- **Estruturação de dados**: As funções `parse_api_response_unyleya` & `parse_api_response_ymed` estruturam os dados em json, conforme o `models.py` nas classes `CourseUnyleya` e `CourseYMED`.

![image](https://github.com/user-attachments/assets/d3bcfcbc-127e-4d88-bc17-85c4130f3681)

## Como executar
1. Crie um ambiente virtual e ative-o.
2. Instale as dependências com `pip install -r requirements.txt`.
3. Defina variáveis de ambiente (por exemplo, `REDIS_URL` e `PIPEFY_API_KEY`).
4. Inicie o servidor com `uvicorn api.main:app --reload`.
5. Acesse `http://localhost:8000` para interagir com a API.

Sinta-se à vontade para explorar o código e contribuir com melhorias.

## Como contribuir

Contribua seguindo os passos abaixo:

1. **Fork e Clone**: Faça um fork do repositório e clone-o localmente:
  ```bash
  git clone https://github.com/danexplore/NPI-backend.git
  ```

2. **Crie uma Branch**: Crie uma branch para suas alterações:
  ```bash
  git checkout -b feature-branch
  ```

3. **Edite e Teste**: Faça suas alterações e teste para garantir que funcionam.

4. **Commit e Push**: Commit e envie suas alterações:
  ```bash
  git add .
  git commit -m "Descrição das alterações"
  git push origin feature-branch
  ```

5. **Abra um Pull Request**: Solicite a revisão no GitHub.

Obrigado por contribuir!

## Licença

Este projeto está licenciado sob a licença MIT. Consulte o arquivo `LICENSE` para mais detalhes.

## Contato

Se você tiver dúvidas, sugestões ou quiser saber mais sobre o projeto, entre em contato:

- **Email**: danielbatistamor@gmail.com
- **LinkedIn**: [Daniel Moreira Batista](https://www.linkedin.com/in/daniel-moreira-87b9b42ba/)
- **GitHub**: [danexplore](https://github.com/danexplore)

Agradecemos por explorar este repositório e esperamos que ele seja útil para você!
