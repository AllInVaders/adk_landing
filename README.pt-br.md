# 🚀 ADK Growth Hacker Agent: Plataforma Multi-Agente Serverless para Landing Pages

| [🇺🇸 English](README.md) | [🇪🇸 Español](README.es.md) | 🇧🇷 **Português (Brasil)** |
| :---: | :---: | :---: |

Bem-vindo à plataforma **ADK Growth Hacker Agent**! Um sistema multi-agente autônomo de nível empresarial construído sobre o **Google Agent Development Kit (ADK)**. Projetado para ajudar fundadores de startups, profissionais de marketing e desenvolvedores a validar ideias de produtos instantaneamente criando landing pages de pré-lançamento de altíssima conversão e realizando o deploy serverless no **Google Cloud Run** em minutos.

O sistema orquestra uma frota especializada de sub-agentes com roteamento inteligente de modelos (**Gemini 2.5 Pro** para síntese criativa de código e **Gemini 2.5 Flash** para operações rápidas), guardrails de segurança, compactação de memória contextual, observabilidade JSON estruturada e **Infraestrutura como Código (IaC) com Terraform**.

---

## 📐 Arquitetura Multi-Agente e Fluxo do Sistema

A plataforma utiliza o padrão **Supervisor-Trabalhador Multi-Agente** com rastreabilidade distribuída:

```mermaid
flowchart TD
    User([👤 Fundador / Marketer]) <--> WebUI[💻 Developer Web UI / FastAPI]
    WebUI <--> Supervisor[🤖 Growth Hacker Supervisor Agent\ngemini-2.5-flash]
    
    subgraph MultiAgentTeam [Frota Especializada de Sub-Agentes]
        Supervisor <-->|Copywriting Estratégico e Código| Architect[🎨 Landing Page Architect Agent\ngemini-2.5-pro]
        Supervisor <-->|Provisionamento e Verificação no Cloud Run| Deployer[☁️ Cloud Deployer Agent\ngemini-2.5-flash]
        Supervisor <-->|Análise de Logs e Extração de Leads| Analytics[📊 Lead Analytics Agent\ngemini-2.5-flash]
    end

    subgraph SecurityAndMemory [Serviços Centrais da Plataforma]
        Guardrails[🛡️ Guardrails de Segurança e HITL]
        Compactor[🧠 Compactação Contextual e Memória Assíncrona]
        Observer[📈 Logger JSON Estruturado e Anonimização PII]
    end

    Architect --> LocalFS[(📁 Sistema de Arquivos Local /deployments/)]
    Deployer --> CloudRun[(☁️ Google Cloud Run Serverless)]
    Analytics --> CloudLog[(📋 GCP Cloud Logging)]
```

---

## 🚀 Início Rápido

```bash
# Ativar ambiente virtual e instalar dependências
source .venv/bin/activate
pip install -r requirements.txt

# Executar a suíte de testes e o harness de avaliação do Golden Dataset
python -m unittest discover tests
python -m eval.eval_harness

# Iniciar a interface web do desenvolvedor
python main.py
```
Acesse no seu navegador em **`http://localhost:8080/`**.
