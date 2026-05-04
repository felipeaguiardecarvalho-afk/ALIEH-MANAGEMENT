# Comparação minuciosa: **Clientes** (Streamlit) × **`/customers`** (protótipo Next)

**Data do relatório:** 2026-05-03  
**Última actualização:** 2026-05-03 — **revisão 2:** paridade funcional reforçada — ordenação numérica do código na API; validação e normalização (nome, CEP, CPF, e-mail, telefone) no **backend** antes de `POST`/`PUT`; leituras `GET` com **viewer**; remoção de `requireDatabase()` nas *server actions*; mensagem de sucesso ao criar com **código** devolvido pela API; `customers-api` com `apiPrototypeFetchRead` + `no-store` nas leituras.

**Âmbito:** secção **Clientes** no `app.py` (`elif page == PAGE_CLIENTES:`) frente às rotas **`/customers`**, **`/customers/new`** e **`/customers/[id]/edit`** em **`web-prototype`**, com dados e mutações via **`api-prototype`** (`routes/customers.py`, `customers_read.py`, `customers_validate.py`) e *server actions* em **`lib/actions/customers.ts`**.

**Referências principais**

| Camada | Ficheiros |
|--------|-----------|
| Streamlit | `app.py` (aprox. linhas 2259–2701), `fetch_viacep_address`, `init_cust_edit_session`; `services.customer_service` (`insert_customer_row`, `update_customer_row`, `delete_customer_row`); `services.read_queries.fetch_customers_ordered` → `database.repositories.query_repository.fetch_customers_ordered`; `utils.validators` (CPF, CEP, e-mail); `utils.rbac` (`require_operator_or_admin`, `require_admin`) |
| Protótipo — lista | `web-prototype/app/(main)/customers/page.tsx`, `customer-row-actions.tsx` |
| Protótipo — criação | `web-prototype/app/(main)/customers/new/page.tsx`, `new-customer-form.tsx` |
| Protótipo — edição | `web-prototype/app/(main)/customers/[id]/edit/page.tsx`, `edit-customer-form.tsx` |
| Protótipo — partilhado | `web-prototype/components/customer-cep-block.tsx` |
| Protótipo — API cliente | `web-prototype/lib/customers-api.ts` |
| Protótipo — acções | `web-prototype/lib/actions/customers.ts`, `web-prototype/lib/rbac.ts` |
| API | `api-prototype/routes/customers.py`, `api-prototype/customers_read.py`, **`api-prototype/customers_validate.py`** |

---

## 1. Resumo executivo

| Dimensão | Streamlit | Protótipo Next |
|----------|-----------|----------------|
| **Arquitectura de UI** | Uma página com **abas** (*Cadastrar* / *Editar cliente*); listagem na aba Cadastrar abaixo do formulário. | **Lista** dedicada em `/customers`; **criação** em `/customers/new`; **edição** em `/customers/[id]/edit` (rotas separadas). |
| **Fonte da listagem** | `fetch_customers_ordered()` com `sql_numeric_sort_key_text("customer_code")`. | `GET /customers` → `list_customers` com a **mesma** expressão `ORDER BY` (paridade com `query_repository.fetch_customers_ordered`). |
| **Colunas na grelha resumida** | Código, Nome, CPF, Telefone, Cidade, **CEP**, Atualizado. | Código, Nome, CPF, Telefone, Cidade, Atualizado (**sem coluna CEP** na tabela — diferença de UI/densidade). |
| **ViaCEP** | Botão **fora** do `st.form`; preenche `session_state` e `st.rerun()`. | Botão **fora** do submit HTML; estado React preenche `defaultValue` dos inputs nomeados; **8 dígitos** obrigatórios antes do pedido HTTP ao ViaCEP. |
| **Validação antes de gravar** | Nome; CEP 8 dígitos se preenchido; CPF + `validate_cpf_br`; e-mail opcional válido; telefone normalizado — no **Streamlit** antes de chamar o serviço. | **API** (`prepare_customer_write_fields` em `customers_validate.py`): mesmas regras conceptuais + **CPF e telefone só dígitos** na persistência; *server action* ainda verifica nome vazio como *fast fail* antes do POST. |
| **RBAC — criar / actualizar** | `require_operator_or_admin()` antes de insert/update. | `requireOperator()` + `gateMutation()`; API `POST`/`PUT` com `Depends(get_actor)` (**admin ou operador**). |
| **RBAC — eliminar** | `require_admin()` antes de `delete_customer_row`. | `requireAdmin()` na acção; API `DELETE` com `Depends(get_admin_actor)`. UI: **Eliminar** só se `isAdmin`. |
| **RBAC — ver listagem / ficha (leitura)** | Qualquer sessão com acesso ao menu vê a página. | **`GET /customers`** e **`GET /customers/{id}`** com `Depends(get_actor_read)` — **admin, operador e viewer** (viewer não grava). |
| **Sucesso ao criar** | Mensagem com **código** + limpeza de `session_state` + `st.rerun()`. | Mensagem *«Cliente cadastrado. Código {customer_code}.»* a partir do JSON da API; `revalidatePath("/customers")`; sem `redirect` automático. |
| **Pré-condição `DATABASE_URL` no Next** | N/A (app Python fala com a BD). | **Removida:** *mutations* não exigem `DATABASE_URL` no ambiente Next — só `API_PROTOTYPE_URL` e sessão com papel adequado. |
| **Sucesso ao editar** | *«Cliente atualizado.»* + `rerun`. | *«Cliente actualizado.»*; `revalidatePath`. |
| **Sucesso ao eliminar** | `_cust_deleted_ok` + `rerun`. | `redirect("/customers")`. |
| **Cache Next** | N/A | `revalidate = 30` nas páginas; leituras `GET` com `cache: "no-store"` em `customers-api.ts`. |

---

## 2. Modelo de navegação e fluxo de trabalho

### 2.1 Streamlit

- Título **«### Clientes»** e *caption* explicando ViaCEP, tabela `customers` e geração automática do código.
- `st.tabs(["Cadastrar", "Editar cliente"])`.
- **Aba Cadastrar:** formulário de novo cliente + divisor + **«#### Todos os clientes»** com `st.dataframe` (ou *caption* se vazio).
- **Aba Editar:** *selectbox* por rótulo `"{customer_code} — {name}"`; formulário de edição por `id`; secção **Excluir cadastro** com fluxo em dois passos (abrir confirmação → Sim/Cancelar).

### 2.2 Protótipo

- **`/customers`:** *PageHero* CRM + botão **Cadastrar cliente** → `/customers/new`; cartão com tabela ou estado vazio com link **Criar o primeiro**.
- **`/customers/new`:** *PageHero* + cartão com `NewCustomerForm`.
- **`/customers/[id]/edit`:** *PageHero* com código + botão voltar; `EditCustomerForm` com zona de administração para eliminação.

**Conclusão:** funcionalidade equivalente repartida por **rotas** em vez de **abas**; o utilizador precisa de mais cliques para alternar entre «lista global» e «ficha», mas o conjunto de operações cobre o mesmo universo (CRUD + ViaCEP).

---

## 3. Listagem de clientes

### 3.1 Ordenação

| Origem | Ordenação |
|--------|-----------|
| **Streamlit** (`fetch_customers_ordered`) | `ORDER BY` com `sql_numeric_sort_key_text("customer_code")` — chave **numérica** (REAL) com vazio → 0. |
| **API** (`list_customers`) | **Idem:** `order_expr = sql_numeric_sort_key_text("customer_code")` interpolado no SQL — **paridade** com Streamlit. |

### 3.2 Colunas apresentadas

| Campo | Streamlit (*dataframe*) | Protótipo (tabela) |
|-------|-------------------------|-------------------|
| Código | Sim | Sim (estilo mono / destaque) |
| Nome | Sim | Sim (*line-clamp* + `title`) |
| CPF | Bruto ou vazio → «—» | Formatação **XXX.XXX.XXX-XX** se 11 dígitos; caso contrário texto tal qual |
| Telefone | Sim | Sim |
| Cidade | Sim | Sim |
| **CEP** | Sim | **Não** (dado continua na API / edição) |
| Atualizado | `updated_at` ou «—» | `formatDate(updated_at)` ou `created_at` se `updated_at` ausente, senão «—» |

### 3.3 Estado vazio

- **Streamlit:** *«Nenhum cliente ainda.»* (*caption*) na listagem; na aba Editar: *«Nenhum cliente — cadastre na aba Cadastrar.»* (`st.info`).
- **Protótipo:** parágrafo centrado com link para `/customers/new`.

---

## 4. Novo cliente (cadastro)

### 4.1 Campos e validação

Ambos cobrem os mesmos campos persistidos na tabela `customers`: nome, CPF, RG, telefone, e-mail, Instagram, CEP, logradouro, número, bairro, cidade, UF, país.

| Detalhe | Streamlit | Protótipo |
|---------|-----------|-----------|
| Nome | Obrigatório; validado no submit | HTML `required` + verificação na *action* + **API** (`prepare_customer_write_fields`) |
| CPF | `normalize_cpf_digits` + `validate_cpf_br` | **API:** dígitos + validação BR antes de `insert_customer_row` |
| Telefone | `normalize_phone_digits` | **API:** só dígitos gravados |
| E-mail | `validate_email_optional` | **API:** regex alinhada ao `validate_email_optional` |
| CEP | `sanitize_cep_digits`; se preenchido → 8 dígitos | **API:** idem; **browser:** ViaCEP só com 8 dígitos |
| País | *Placeholder* «Brasil» | `ALIEH_DEFAULT_COUNTRY` ou vazio na *action*; API grava *strip* ou `None` |
| Código do cliente | Mensagem de sucesso com código | Mensagem *«Cliente cadastrado. Código {code}.»* |

**Nota técnica:** `customers_validate.py` **não** importa `utils.validators` (ciclo `database` ↔ `validators` ao arrancar a API); contém cópia **mínima** das funções de CPF/CEP/e-mail/telefone espelhando o comportamento.

### 4.2 ViaCEP

| Aspecto | Streamlit | Protótipo |
|---------|-----------|-----------|
| URL | `https://viacep.com.br/ws/{digits}/json/` | Idem (fetch no browser) |
| Validação de comprimento | 8 dígitos antes do pedido | Idem (`CustomerCepBlock`) |
| User-Agent | `ALIEH-management/1.0` | Browser default |
| Timeout | 12 s (`urlopen`) | Default `fetch` |

### 4.3 Gravação

- **`services.customer_service.insert_customer_row`** (Streamlit directo; API `POST` após `prepare_customer_write_fields`).

**Duplicidade:** inalterada no serviço (CPF / telefone no *tenant*).

---

## 5. Editar cliente

### 5.1 Selecção do registo

- **Streamlit:** *selectbox* + `init_cust_edit_session`.
- **Protótipo:** URL `/customers/[id]/edit`; `GET /customers/{id}` com `get_actor_read` (viewer pode **abrir** a ficha; `PUT` continua a exigir operador/admin).

### 5.2 Validação no submit

- **Streamlit:** mesmas regras que no cadastro + `update_customer_row`.
- **Protótipo:** **`PUT`** passa pelo mesmo `prepare_customer_write_fields` que o **POST**.

### 5.3 Rotulagem de botões

- Streamlit: **«Salvar alterações»**.
- Protótipo: **«Guardar alterações»** (diferença lexical, não de regra).

### 5.4 Eliminação

- Streamlit: fluxo em duas fases + `require_admin` no «Sim».
- Protótipo: `ConfirmDeleteForm` + `requireAdmin` / `get_admin_actor`.

---

## 6. Eliminação a partir da lista

- **Streamlit:** só na aba Editar.
- **Protótipo:** atalho na lista para **admin** (mesma API e regra de vendas).

---

## 7. API REST (`api-prototype`)

| Método | Rota | Actor | Notas |
|--------|------|-------|--------|
| GET | `/customers` | **`get_actor_read`** (admin, operator, **viewer**) | `{ items: [...] }` |
| GET | `/customers/{id}` | **`get_actor_read`** | 404 fora do *tenant* |
| POST | `/customers` | `get_actor` | Corpo validado por `prepare_customer_write_fields` → `insert_customer_row` → `{ customer_code }` |
| PUT | `/customers/{id}` | `get_actor` | Idem validação → `update_customer_row` |
| DELETE | `/customers/{id}` | `get_admin_actor` | |

---

## 8. Matriz de paridade (resumo)

| Funcionalidade | Streamlit | Protótipo (revisão 2) |
|----------------|-----------|------------------------|
| Listar clientes do *tenant* | Sim | Sim |
| Ordem numérica do `customer_code` | Sim | Sim |
| Coluna CEP na lista | Sim | Não (UI) |
| Criar com ViaCEP | Sim | Sim |
| Validar CPF / CEP / e-mail antes de gravar | Sim | Sim (**API**) |
| Normalizar CPF / telefone na gravação | Sim | Sim (**API**) |
| Operador/admin para criar/editar | Sim | Sim |
| Admin para apagar | Sim | Sim |
| Viewer ver lista / GET ficha | Implícito no menu | Sim (`get_actor_read`) |
| Bloqueio com vendas vinculadas | Sim | Sim |
| Mensagem com código ao criar | Sim | Sim |
| Mutações sem `DATABASE_URL` no Next | N/A | Sim |
| Duas etapas visuais vs `window.confirm` | Streamlit | Next (diferença de UI) |

---

## 9. Conclusão

Após a **revisão 2**, o protótipo alinha com o Streamlit nas **regras de negócio visíveis ao utilizador**: ordenação da lista, **validação e normalização no servidor** antes de persistir, **leitura para viewer**, **mensagem com código** ao criar, e **cadastro/edição/exclusão** sem depender de `DATABASE_URL` no Next. **Diferenças residuais** são sobretudo de **apresentação** (abas vs rotas, coluna CEP na grelha, rótulos de botões, fluxo visual de confirmação de exclusão, UA/timeout do ViaCEP no browser).

---

## 10. Itens opcionais remanescentes

1. Mostrar **CEP** na tabela da lista (paridade visual com o *dataframe* Streamlit).  
2. Opcional: alinhar texto do botão de edição a **«Salvar alterações»** (apenas cópia, sem mudar layout).  
3. Opcional: `User-Agent` / timeout na chamada ViaCEP no servidor (hoje só no cliente).

---

## 11. Registo de alterações (revisão 2)

| Área | Alteração |
|------|-----------|
| `customers_read.py` | `ORDER BY` com `sql_numeric_sort_key_text("customer_code")`. |
| `customers_validate.py` | Novo: validação/norm. espelhando Streamlit antes de `POST`/`PUT`. |
| `routes/customers.py` | `get_actor_read` nos GET; `prepare_customer_write_fields` em POST/PUT. |
| `lib/customers-api.ts` | `apiPrototypeFetchRead` + `no-store` para listas e detalhe. |
| `lib/actions/customers.ts` | Remoção de `requireDatabase`; mensagem de sucesso com `customer_code`. |

---

*Fim do relatório.*
