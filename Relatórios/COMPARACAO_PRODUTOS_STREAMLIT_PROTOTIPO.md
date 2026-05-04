# Comparação minuciosa: **Produtos** (Streamlit produção) × **`/products`** (protótipo web)

**Data do relatório:** 2026-05-03 — **última actualização:** 2026-05-03 (paridade UX: paginação numérica, filtros com debounce, feedback de sucesso/selecção, ordem de atributos unificada, mensagens de erro da API).  
**Âmbito:** módulo **Produtos** na aplicação Streamlit (`app.py`, página `PAGE_PRODUTOS`) frente às UIs Next que expõem **`/products`** consumindo a **`api-prototype`** (`GET/PUT/PATCH/DELETE` em `/products`…).

**Superfícies Next no repositório (paridade de produtos):**

| Pacote | Comando típico | `/products` |
|--------|----------------|--------------|
| **`web-prototype/`** | `npm run dev:prototype` (porta configurável, ex. 3000 no seu `.env.local`) | Fluxo completo desde o início do trabalho de migração UI. |
| **Raiz do repo** | `npm run dev` → `next dev -p 3000` | **Mesmo fluxo completo** copiado para `app/products/*`, `lib/products-api.ts`, `lib/actions/products.ts`, etc. (sem depender de importar código de `web-prototype/` — `tsconfig` exclui esse pacote). |

Em **desenvolvimento local** (`next dev` na raiz), se `API_PROTOTYPE_URL` / `API_PROTOTYPE_USER_ID` não estiverem definidos, o Next usa por omissão **`http://127.0.0.1:8000`** e utilizador **`1`**, e resolve perfil **`admin`** quando não existe cookie `alieh_role` (ver `lib/api-prototype.ts` e `lib/tenant.ts`). Para subir a API: **`npm run dev:api`** (uvicorn em `api-prototype/`). Em **produção** (`next build` / `next start`) esses atalhos **não** aplicam — é obrigatório configurar URL, actor e cookies conforme ambiente.

---

## Índice

1. [Resumo executivo](#1-resumo-executivo)
2. [Arquitetura e camadas de dados](#2-arquitetura-e-camadas-de-dados)
3. [Estrutura da página e navegação](#3-estrutura-da-página-e-navegação)
4. [Busca, ordenação e filtros por atributo](#4-busca-ordenação-e-filtros-por-atributo)
5. [Paginação e contagem de resultados](#5-paginação-e-contagem-de-resultados)
6. [Tabela / grelha de produtos](#6-tabela--grelha-de-produtos)
7. [Seleção do produto e descoberta do detalhe](#7-seleção-do-produto-e-descoberta-do-detalhe)
8. [Painel de detalhe: identificação e atributos](#8-painel-de-detalhe-identificação-e-atributos)
9. [Imagem do produto (visualização e substituição)](#9-imagem-do-produto-visualização-e-substituição)
10. [Edição do lote: nome, data de registo e atributos](#10-edição-do-lote-nome-data-de-registo-e-atributos)
11. [Bloqueio de edição de lote (`lot_edit_block`)](#11-bloqueio-de-edição-de-lote-lot_edit_block)
12. [Exclusão permanente de SKU](#12-exclusão-permanente-de-sku)
13. [Cadastro de novo produto (lote + SKU derivado)](#13-cadastro-de-novo-produto-lote--sku-derivado)
14. [RBAC: administrador vs operador](#14-rbac-administrador-vs-operador)
15. [Atualização de dados e cache](#15-atualização-de-dados-e-cache)
16. [Mensagens de sucesso, erro e estados vazios](#16-mensagens-de-sucesso-erro-e-estados-vazios)
17. [Matriz de paridade (checklist)](#17-matriz-de-paridade-checklist)
18. [Diferenças inevitáveis ou aceites](#18-diferenças-inevitáveis-ou-aceites)
19. [Referência de ficheiros](#19-referência-de-ficheiros)

---

## 1. Resumo executivo

| Critério | Streamlit (produção) | Protótipo (`/products` — **web-prototype** ou **Next na raiz**) |
|----------|----------------------|----------------------------------------|
| **Objetivo do módulo** | Catálogo de lotes/produtos por SKU; detalhe; edição; exclusão de SKU; cadastro de novos lotes. | Idem, com UI web e mesma semântica de negócio via **API** e mesmos tipos de operação. |
| **Paridade funcional global** | Referência. | **Alta** nas duas apps Next: busca, filtros, ordenação, paginação, colunas da grelha, detalhe, foto, edição de lote, bloqueios, exclusão SKU (com confirmação em duas fases), cadastro, RBAC. |
| **Paridade de UX** | Uma página contínua; widgets reactivos; expanders. | URL com querystring; painel lateral; **filtros reactivos** (debounce ~450 ms + `router.push`, com botão «Aplicar filtros»); **paginação** com campo numérico de página + Anterior/Seguinte; **toasts** de sucesso e aviso ao seleccionar produto; cadastro no fim e `/products/new`; na raiz, `/products/[id]` → `?detail=`. |
| **Autenticação / actor na API** | Sessão Streamlit + código Python. | **web-prototype:** JWT em cookie via `getSession()`. **Raiz:** cabeçalhos `X-User-Id` / `X-Username` a partir de cookies `alieh_*` ou variáveis `API_PROTOTYPE_*`; em `next dev`, fallbacks locais (ver cabeçalho deste documento). |

Em termos de **regras de negócio** (o que pode ou não editar, apagar, cadastrar), o protótipo foi desenhado para seguir o Streamlit, delegando persistência na **api-prototype**, que por sua vez usa repositórios/checagens equivalentes (ex.: bloqueio de edição de lote, bloqueio de exclusão de SKU, pré-visualização do corpo de SKU).

---

## 2. Arquitetura e camadas de dados

### 2.1 Streamlit (produção)

- O browser corre a app **Streamlit** em Python.
- A página **Produtos** chama funções Python directamente sobre a base (ex.: `search_products_filtered`, `fetch_product_by_id`, `add_product`, `update_product_lot_attributes`, `update_product_lot_photo`, `hard_delete_sku_catalog`, `product_lot_edit_block_reason`, `sku_correction_block_reason`), conforme `app.py` (bloco `if page == PAGE_PRODUTOS:`).

### 2.2 Protótipo (Next)

- O browser corre **Next.js** — seja em **`web-prototype/`**, seja na **raiz** do repositório (`npm run dev` na raiz, porta **3000** por omissão no `package.json` actual).
- O servidor Next chama a **`api-prototype`** (FastAPI) com cabeçalhos de inquilino/utilizador (`prototypeAuthHeaders` / `prototypeAuthHeadersRead`), por exemplo:
  - `GET /products` — lista filtrada e paginada;
  - `GET /products/attribute-options`;
  - `GET /products/{id}` — detalhe + `lot_edit_block_reason` + `sku_delete_block_reason`;
  - `GET /products/{id}/image` — ficheiro em disco, quando aplicável;
  - `PUT /products/{id}/attributes`;
  - `PATCH /products/{id}/image-bytes`;
  - `POST /products` — cadastro;
  - `DELETE /products/sku?sku=…` — exclusão de SKU (actor admin).

**Consequência:** o protótipo depende da **API estar acessível** na URL configurada. Em **produção** isso implica **`API_PROTOTYPE_URL`** (e identificação do actor). Em **`next dev` na raiz**, a URL e o user id têm **valores por omissão** locais se as variáveis faltarem (ver introdução). O Streamlit depende da base/credenciais directamente no runtime Streamlit. O comportamento observado pelo utilizador deve ser o mesmo quando a API e o Streamlit apontam ao **mesmo** inquilino e dados.

### 2.3 Diferença mínima entre `web-prototype` e Next na raiz

- **`web-prototype`:** `lib/api-prototype.ts` obtém utilizador a partir da **sessão JWT** (`getSession()`); modo aberto `ALIEH_PROTOTYPE_OPEN=1` com fallback `API_PROTOTYPE_USER_ID`.
- **Raiz:** `lib/api-prototype.ts` usa **cookies** `alieh_user_id` / `alieh_username` (e env `API_PROTOTYPE_*`) + `resolveTenantId` / `resolveRole` de `lib/tenant.ts`; em desenvolvimento aplica os defaults descritos no cabeçalho. Variável **`ALIEH_DEV_ROLE`** (opcional) força `admin` | `operator` | `viewer` em `next dev` quando não há cookie `alieh_role`.

---

## 3. Estrutura da página e navegação

### 3.1 Streamlit

- Título: `### Produtos`.
- Legenda inicial: *«Use **Busca por SKU** para localizar lotes ou cadastre novos abaixo.»*
- **Expander** «Busca por SKU e lote», **fechado por omissão** (`expanded=False`), concentra busca, filtros, paginação, tabela e select de detalhe.
- Abaixo do expander (fora dele), secção **«### Cadastro de produto»** com legenda longa e campos de registo na **mesma página** (scroll vertical único).

### 3.2 Protótipo (equivalente em `web-prototype` e na raiz)

- **Page hero** com título «Produtos», descrição em texto simples (sem Markdown no componente), acções:
  - **Cadastrar produto** → link para a âncora `#cadastro-produto` na mesma URL (preserva query de filtros, remove `detail` da construção do link onde aplicável).
  - **Atualizar** → *server action* `refreshProducts` (`revalidatePath` de `/products` e `/dashboard`).
- **Cartão** «Busca por SKU e lote» (`ProductsFilters`, componente **client**): equivalente conceptual ao expander do Streamlit, mas **sempre visível**; aplica filtros à URL após debounce (comportamento próximo do rerun do Streamlit) e mantém **«Aplicar filtros»** / **«Limpar»**.
- **Cartão** «Resultados» com tabela e barra de paginação.
- **Painel lateral** (`ProductDetailAside`) quando `?detail=<id>` está presente e o detalhe carrega com sucesso.
- **Cartão** «Cadastro de produto» no **fim** da página, com texto alinhado ao `st.caption` do Streamlit (lotes novos, foto opcional, stock em Estoque, regras de duplicidade, custo em Custos). Há ainda link para **`/products/new`** (vista só do formulário).

**Diferença de UX:** no Streamlit, busca e cadastro coexistem no fluxo visual «expander fechado + scroll»; no protótipo, busca está sempre expandida e o cadastro está ancorado no fim (mais próximo de uma SPA com âncoras).

---

## 4. Busca, ordenação e filtros por atributo

### 4.1 Texto de busca (SKU ou nome)

| Aspecto | Streamlit | Protótipo |
|---------|-----------|-----------|
| **Rótulo** | «Buscar SKU ou nome» | «Busca (SKU ou nome)» (`q`) |
| **Placeholder** | `ex.: 001, SUN, parte do nome…` | `Ex.: ARX- ou óculos` |
| **Semântica** | Busca parcial em SKU ou nome; combinável com filtros. | Igual, enviada como query `q` em `GET /products`. |
| **Actualização** | A cada rerun do Streamlit (mudança de widget). | **Debounce (~450 ms)** ao alterar busca, ordenação, «por página» ou qualquer atributo → `router.push` com query actualizada (página reposta em **1**); **«Aplicar filtros»** força já; links de paginação/detalhe preservam a query. |

### 4.2 Ordenação (`sort`)

Valores suportados (alinhados com a API / repositório):

| Valor | Rótulo Streamlit | Rótulo protótipo |
|-------|------------------|------------------|
| `sku` | SKU (A–Z) | SKU (A–Z) |
| `name` | Nome (A–Z) | Nome (A–Z) |
| `stock_desc` | Estoque (maior → menor) | Estoque (maior) |
| `stock_asc` | Estoque (menor → maior) | Estoque (menor) |

**Diferença cosmética:** setas «→» no Streamlit; no protótipo texto curto.

### 4.3 Filtros por atributo

| Dimensão | Streamlit | Protótipo |
|----------|-----------|-----------|
| **Cor da armação** | `selectbox` com `FILTER_ANY` + opções `attr_opts["frame_color"]` | `<select name="frame_color">` com «Todos» (`""`) + lista |
| **Cor da lente** | idem `lens_color` | idem `lens_color` |
| **Gênero** | idem `gender` | idem `gender` |
| **Paleta** | idem `palette` | idem `palette` |
| **Estilo** | idem `style` | idem `style` |
| **Disposição** | Cinco colunas numa linha dentro do expander. | Grelha responsiva dentro de `<details>` «Filtros por atributo» (opcional — expandir). **Ordem canónica no protótipo (filtros, cadastro, edição, detalhe, tabela):** armação → lente → género → paleta → estilo (alinhada às colunas da grelha e ao `dl` do painel). *Nota:* no `st.form` do Streamlit a ordem dos selectboxes de edição é armação, lente, **paleta**, **género**, estilo — diferença puramente visual de ordem nos widgets Streamlit vs ordem unificada no protótipo. |
| **Origem das opções** | `fetch_product_search_attribute_options()` | `GET /products/attribute-options` fundido com listas de domínio (`mergeDomainWithApiAttributeOptions`) para incluir valores canónicos + valores já existentes na base. |

### 4.4 «Limpar» filtros

- **Streamlit:** não há botão único «limpar»; o utilizador repõe widgets.
- **Protótipo:** link **«Limpar»** → `/products` sem query (recomeça do zero).

---

## 5. Paginação e contagem de resultados

### 5.1 Tamanho de página

- **Streamlit:** `[25, 50, 100, 200]`, índice por omissão **2** → **100** linhas.
- **Protótipo:** mesmas opções; omissão **`page_size=100`** se não vier na URL.

### 5.2 Número de página

- **Streamlit:** `st.number_input` «Página», com `min`/`max` derivados de `total_match` e `page_size`; métrica «Resultados» com `total_match`; legenda «Página X / Y · N linha(s)…».
- **Protótipo:** `page` na querystring; barra **«Página X de Y · N registo(s)»**; campo numérico **«Página»** (`input type="number"`, `min=1`, `max=total_pages`) com **Enter** ou **blur** para navegar (valor **clamp** ao intervalo válido); botões **Anterior** / **Seguinte** (links).

**Paridade:** salto directo para página N (ex.: 50) equivale ao Streamlit; a URL reflecte `?page=50` mantendo os restantes parâmetros do catálogo.

### 5.3 Contagem total

- Ambos derivam o total da mesma família de consulta filtrada (`search_products_filtered` no backend comum via repositório na API).

---

## 6. Tabela / grelha de produtos

### 6.1 Colunas (ordem e significado)

O `st.dataframe` do Streamlit usa colunas equivalentes às do protótipo após o trabalho de alinhamento:

| Coluna Streamlit | Protótipo | Notas |
|------------------|------------|-------|
| ID | ID | Numérico. |
| SKU | SKU (badge) | «—» no Streamlit vs «—» / badge no protótipo. |
| Nome | Nome | Texto; células largas máx. no protótipo. |
| Cor armação | Cor armação | |
| Cor lente | Cor lente | |
| Gênero | Gênero | |
| Paleta | Paleta | |
| Estilo | Estilo | |
| Criado em | Criado em | Streamlit: `format_product_created_display`; protótipo: `formatDate` (locale pt-BR). |
| Estoque | Estoque | Streamlit: `NumberColumn(format="%.4f")`; protótipo: `formatProductStock` (até 4 casas decimais, `pt-BR`). |
| Custo médio | Custo médio | Streamlit: `%.2f`; protótipo: `formatProductMoney` (BRL, 2 casas). |
| Preço | Preço | Idem. |

### 6.2 Estado vazio

- **Streamlit:** `st.info("Nenhum produto com esses filtros.")`.
- **Protótipo:** parágrafo «Nenhum produto com esses filtros.» na área da tabela.

---

## 7. Seleção do produto e descoberta do detalhe

### 7.1 Streamlit

- Após a tabela: `selectbox` **«Selecionar produto (detalhes)»** com opção inicial «—» e etiquetas `id | sku | nome`.
- Ao escolher uma linha: `st.success` com ID e SKU; abre **container** com imagem + markdown de campos; secções seguintes (editar, apagar) no mesmo fluxo vertical.

### 7.2 Protótipo

- Cada linha tem botão/link **«Detalhe»** que define `?detail=<id>` mantendo os filtros/página na query.
- **Painel lateral fixo** (overlay + `aside`) com botão **Fechar** (remove `detail` da URL).
- **Aviso curto ao abrir detalhe** (`ProductSelectionToast`): mensagem do tipo *«Produto selecionado: {nome} (SKU: …)»*, auto-oculta (~2,8 s), sem alterar layout do painel.
- O título do painel continua a mostrar nome + badges SKU/código.

**Paridade:** inspeccção dos mesmos campos de negócio; o aviso aproxima o feedback de `st.success` ao seleccionar no Streamlit.

---

## 8. Painel de detalhe: identificação e atributos

### 8.1 Campos mostrados

| Campo | Streamlit (markdown no detalhe) | Protótipo (`ProductDetailAside`) |
|-------|----------------------------------|----------------------------------|
| SKU | Sim | Secção identificação + badge |
| Nome | Sim | Sim |
| Atributos | Uma linha «Cor armação · … · Estilo» | Lista `dl` + badges (ordem: armação, lente, género, paleta, estilo) |
| Estoque | `format_qty_display_4` | `formatProductStock` |
| Custo médio (SKU) | `format_money` | `formatProductMoney` |
| Preço (SKU) | idem | idem |
| Código de entrada | Sim | Sim |
| **Data de registo** | **Não** aparece explicitamente no bloco markdown (há rótulo «Cadastro (registro)» ligado a **`created_at`**) | **`registered_date`** e **`created_at`** em campos distintos (**mais claro** que o rótulo ambíguo do Streamlit). |

### 8.2 Navegação para outros módulos

- **Streamlit:** legenda em texto: usar SKU em Estoque, Custos, Precificação, Vendas.
- **Protótipo:** cartão **«Atalhos»** com botões para `Estoque` (com `?q=` no código de entrada ou SKU), `Custos`, `Precificação`, `Nova venda` (`/sales/new`).

---

## 9. Imagem do produto (visualização e substituição)

### 9.1 Visualização

- **Streamlit:** `product_image_abs_path` + `st.image` se existir ficheiro em disco; senão «Sem foto cadastrada.»
- **Protótipo:** se path for URL http(s) ou relativo servido, usa `href` directo; se for path em disco, o SSR obtém **data URL** via `GET /products/{id}/image` (`fetchPrototypeProductDiskImageDataUrl`).

### 9.2 Substituição de foto

- **Streamlit:** dentro do expander «Editar produto»; `file_uploader` + botão «Gravar nova foto»; só **admin** (`disabled=not is_admin()`); tipos jpg/jpeg/png/webp; mensagem de que pode substituir mesmo com stock/custo/preço/vendas.
- **Protótipo:** secção **«Substituir foto do lote»** (`ProductLotPhotoForm`); input `type=file` + submit; **operador** vê UI desactivada e texto de que só admin grava; admin chama `updateProductLotPhoto` → `PATCH .../image-bytes`; sucesso com toast **«Imagem do lote atualizada com sucesso.»**; erros com texto da API no `FormAlert`.

**Paridade:** sim, com separação explícita de fluxo «escolher ficheiro» vs «gravar» no Streamlit num único botão de gravação.

---

## 10. Edição do lote: nome, data de registo e atributos

### 10.1 Streamlit

- Subsecção «Nome, data e atributos».
- Se `product_lot_edit_block_reason(focus_id)` devolver texto → `st.info(block)` e **sem** formulário de edição.
- Caso contrário: opções com `dropdown_with_other` + valores actuais injectados se não estiverem na lista; `st.form` com nome, `date_input` «Data de registro», selectboxes (ordem no form: armação, lente, paleta, género, estilo); botão «Salvar alterações nos dados do lote» **desactivado para não-admin**; submit chama `update_product_lot_attributes` após `require_admin()`.

### 10.2 Protótipo

- **Admin:** `ProductLotEditForm` com `useActionState` → `PUT /products/{id}/attributes` com nome, `registered_date`, atributos na ordem **armação → lente → género → paleta → estilo**; sucesso com toast (`ActionSuccessToast`) e texto devolvido pela API em caso de erro (`FormAlert` só para falhas).
- **Não admin:** texto explicativo + se existir `lot_edit_block_reason`, bloco com `MarkdownHint` (suporta `**negrito**` como no Streamlit).

**Nota:** ordem dos selects no `st.form` Streamlit (armação, lente, paleta, género, estilo) difere da ordem canónica do protótipo; a semântica dos campos e a API são as mesmas.

---

## 11. Bloqueio de edição de lote (`lot_edit_block`)

- **Fonte Streamlit:** `product_lot_edit_block_reason(focus_id)`.
- **Fonte protótipo:** campo `lot_edit_block_reason` em `GET /products/{id}` (mesma família de regra no repositório Python).

**Paridade:** o texto de bloqueio deve coincidir quando a mesma base e inquilino forem usados.

---

## 12. Exclusão permanente de SKU

### 12.1 Regra de bloqueio

- **Streamlit:** `sku_correction_block_reason(sku_key)`; se houver bloqueio → `st.info(block)`; botão «Excluir SKU» **desactivado** se `block` ou **não admin**.
- **Protótipo:** `sku_delete_block_reason` no JSON de detalhe; mensagem com `MarkdownHint`; operador vê secção de administração com botão **«Excluir SKU (bloqueado)»** e texto explicativo; admin só consegue confirmar se não houver bloqueio.

### 12.2 Fluxo de confirmação

- **Streamlit:** primeiro clique em «Excluir SKU» (se habilitado) → estado `prod_sku_del_confirm` → `st.warning` com texto de confirmação → botões **«Sim, excluir SKU»** e **«Cancelar»**; sucesso → mensagem `st.success` na próxima rerun + reset do select.
- **Protótipo:** primeiro clique **«Excluir SKU»** → painel amarelo com o mesmo tipo de texto; **«Sim, excluir SKU»** submete *server action*; **«Cancelar»** volta ao passo 1; após sucesso **toast** «SKU excluído com sucesso.» (`ActionSuccessToast`) e, após ~3,5 s, **`router.replace`** para `/products` **sem** `detail`, com a mesma query de filtros/página (o `redirect` server-side deixou de ser usado para permitir ver o feedback antes de fechar o painel).

**Paridade:** forte; confirmação em duas fases + feedback visível de sucesso, equivalente ao `st.success` antes de a lista se actualizar.

### 12.3 Nota de API

- A rota `DELETE /products/sku` usa `get_admin_actor` na API (só admin). O Streamlit usa `require_admin()` antes de `hard_delete_sku_catalog`.

---

## 13. Cadastro de novo produto (lote + SKU derivado)

### 13.1 Texto orientador

- O **Streamlit** usa um `st.caption` longo (lotes novos, foto opcional, Estoque para exclusão de stock, duplicados nome+data+atributos, mesmo SKU corpo idêntico, padrão `[SEQ]-[PP]-[FC]-[LC]-[GG]-[PA]-[ST]`, custo/estoque em Custos).
- O **protótipo** reproduz a mesma informação no `CardDescription` do cartão «Cadastro de produto» na página `/products` (com pequenas adaptações: não repete literalmente o padrão de colchetes, indica que o SKU é gerado no servidor).

### 13.2 Campos

| Campo | Streamlit | Protótipo |
|-------|-----------|-----------|
| Nome | `text_input` | `Input` obrigatório |
| Data de registo | `date_input` (hoje por omissão) | `input type=date` com omissão ISO hoje |
| Atributos | `attribute_selectbox` com «outro» | `AttributeSelectWithOther` |
| Ordem visual cadastro | Colunas Streamlit (armação+paleta, etc.) | **Ordem canónica:** armação → lente → género → paleta → estilo (grelha `md:grid-cols-2`); alinhada aos filtros e ao detalhe. |
| Preview SKU | `_maybe_preview_product_sku` → `st.info` com SKU | `previewProductSkuBodyAction` debounced 300 ms → cartão com SKU |
| Foto | `file_uploader` directo para bytes | **Supabase** opcional (`ProductImageUpload` → URL, com toast **«Imagem enviada para o Storage com sucesso.»** após upload) **ou** ficheiro em `<details>` enviado como `product_image_file` (base64 no servidor Next → API) |

### 13.3 Submissão e validação

- **Streamlit:** `resolve_attribute_value` por campo; erros por `st.error`; `require_admin()`; `add_product` com bytes opcionais; sucesso → `st.session_state["prod_reg_success_msg"]` + limpeza de keys + `rerun`.
- **Protótipo:** validação mínima no servidor (`createProduct`); erros com **`readApiError(res)`** no `FormAlert`; sucesso → **toast** (`ActionSuccessToast`) com **«Produto cadastrado com sucesso»** (e código de entrada quando a API devolve); `revalidatePath` de `/products` e `/products/new`; **limpeza do formulário** no cliente (nome, data, atributos, preview SKU, reset do bloco Supabase / ficheiro).

**Paridade:** após sucesso o protótipo replica o comportamento de limpeza do Streamlit (sem depender só de recarregar a página).

### 13.4 Rota `/products/new`

- Existe como **atalho** / vista dedicada; o Streamlit **não** tem URL separada, mas a funcionalidade é a mesma família de campos.

---

## 14. RBAC: administrador vs operador

### 14.1 Streamlit

- Usa `is_admin()` para desactivar uploads, gravação de foto, submit de edição de lote, botão de exclusão SKU e cadastro.
- `require_admin()` em acções mutáveis sensíveis.

### 14.2 Protótipo

- `resolveRole()` no Next; `isAdmin = role === "admin"`.
- **Raiz, `next dev`:** sem cookie `alieh_role`, o perfil por omissão é **`admin`** (cadastro e mutações como no Streamlit com utilizador administrador); use **`ALIEH_DEV_ROLE=viewer`** ou **`operator`** no `.env.local` para testar RBAC. Em produção o omissão continua **`viewer`** (sem cookie).
- **`ALIEH_PROTOTYPE_OPEN=1`:** `requireAdmin()` / operações RBAC nas server actions tornam-se permissivas (modo UAT — só ambientes controlados).
- Server actions: `requireAdmin()` / `gateMutation()` conforme acção.
- **Operador:** vê listagens e detalhe; vê bloqueios; não grava edição/foto/cadastro/SKU delete.

**Paridade:** alinhada ao modelo «operador lê, admin altera/apaga/cadastra».

---

## 15. Atualização de dados e cache

- **Streamlit:** `st.rerun()` após mutações bem-sucedidas.
- **Protótipo:** `revalidatePath` (ex.: `/products`); botão **Atualizar** força revalidação; página com `export const revalidate = 30` (ISR parcial).

---

## 16. Mensagens de sucesso, erro e estados vazios

| Situação | Streamlit | Protótipo |
|----------|-----------|-----------|
| Lista vazia | `st.info` | Texto na tabela |
| Produto inexistente no detalhe | `st.warning` com texto definido | Card âmbar + link «Voltar à lista» (texto alinhado) |
| Erro de lista | (depende do crash global) | Card vermelho «Erro ao carregar lista» com **mensagem devolvida pela API** quando exist (`readApiError` / `throw new Error`); na raiz, texto adicional sobre **`npm run dev:api`** / env em falha. |
| Erro só no detalhe | — | Card vermelho «Erro ao carregar detalhe» **sem** esconder a lista; mensagem da API quando disponível. |
| Sucesso apagar SKU | `st.success` na próxima interacção | **Toast** «SKU excluído com sucesso.» + após ~3,5 s **fecho do painel** (`router.replace` sem `detail`, filtros preservados). |
| Sucesso cadastro | `st.success` com código de entrada | **Toast** + mensagem explícita com código de entrada; formulário reposto. |
| Sucesso editar lote / foto | `st.success` / feedback inline | **Toasts** «Produto atualizado com sucesso.» / «Imagem do lote atualizada com sucesso.» |

---

## 17. Matriz de paridade (checklist)

| Funcionalidade | Streamlit | Protótipo |
|----------------|-----------|-----------|
| Busca texto SKU/nome | ✅ | ✅ |
| Filtros 5 atributos + «qualquer» | ✅ | ✅ («Todos») |
| Ordenação 4 modos | ✅ | ✅ |
| Page size 25–200, default 100 | ✅ | ✅ |
| Paginação por total | ✅ | ✅ (campo numérico + Anterior/Seguinte + URL) |
| Filtros reactivos (debounce) | ✅ (rerun) | ✅ (~450 ms + URL) |
| Salto directo para página N | ✅ | ✅ |
| Feedback ao seleccionar produto | ✅ (`st.success`) | ✅ (`ProductSelectionToast`) |
| Limpar formulário após cadastro | ✅ | ✅ |
| Mensagens de erro da API | ✅ (`st.error` com texto) | ✅ (`readApiError` / `FormAlert`) |
| Colunas grelha alinhadas | ✅ | ✅ |
| Formatação stock 4 / moeda 2 | ✅ | ✅ (`formatProductStock` / `formatProductMoney`) |
| Detalhe com stock/custo/preço/código | ✅ | ✅ (+ datas explícitas) |
| Imagem disco/URL | ✅ | ✅ |
| Substituir foto (admin) | ✅ | ✅ |
| Editar lote (admin) + bloqueio | ✅ | ✅ |
| Excluir SKU + bloqueio + 2 passos | ✅ | ✅ |
| Cadastro + preview SKU | ✅ | ✅ |
| Cadastro só admin | ✅ | ✅ |
| Atalhos outros módulos | Texto | Links |

---

## 18. Diferenças inevitáveis ou aceites

1. **Modelo de execução:** Streamlit rerun vs Next SSR + client components + API HTTP.
2. **URL e partilhamento:** o protótipo permite copiar URL com filtros e `detail`; o Streamlit não.
3. **Actualização em tempo real:** Streamlit «ao mudar widget»; protótipo «debounce + URL» para filtros (próximo do rerun), mais submit explícito e links.
4. **Imagem no cadastro:** Streamlit só bytes directos; protótipo acrescenta caminho Supabase (opcional) para ambientes com Storage.
5. **Datas no detalhe:** o protótipo corrige a ambiguidade «Cadastro (registro)» do Streamlit (que usa `created_at`) separando **data de registo** e **criado em**.
6. **Ordem dos widgets de edição no Streamlit:** paleta antes de género no `st.form`; no protótipo a ordem visual segue **género → paleta → estilo** para alinhar filtros, tabela e detalhe.
7. **Duas apps Next:** manter alterações em sincronia é manual (não há import cruzado da raiz para `web-prototype`); a **fonte de verdade** da API e dos contratos HTTP é partilhada (`api-prototype` + serviços Python na raiz do repo).

---

## 19. Referência de ficheiros

### Streamlit (produção)

- `app.py` — bloco `if page == PAGE_PRODUTOS:` (aprox. linhas 721–1295): UI e chamadas a serviços/repositório.

### Protótipo (Next `web-prototype`)

- `web-prototype/app/(main)/products/page.tsx` — composição da página, dados, cadastro embutido, detalhe.
- `web-prototype/app/(main)/products/products-filters.tsx` — busca, sort, page_size, filtros (client + debounce), `ProductsPaginationBar` (salto de página + links).
- `web-prototype/app/(main)/products/products-table.tsx` — grelha.
- `web-prototype/app/(main)/products/product-selection-toast.tsx` — aviso ao abrir detalhe.
- `web-prototype/app/(main)/products/product-detail-aside.tsx` — painel lateral completo.
- `web-prototype/app/(main)/products/product-lot-edit-form.tsx` — edição de lote (admin).
- `web-prototype/app/(main)/products/product-lot-photo-form.tsx` — foto do lote.
- `web-prototype/app/(main)/products/product-sku-delete-form.tsx` — fluxo de exclusão SKU.
- `web-prototype/app/(main)/products/new/new-product-form.tsx` e `new/page.tsx` — cadastro reutilizado.
- `web-prototype/components/action-success-toast.tsx` — toasts de sucesso (auto-dismiss).
- `web-prototype/components/form-status.tsx` — `FormAlert` (erros persistentes; sucessos também podem usar toasts nas páginas de produtos).
- `web-prototype/components/product-image-upload.tsx` — upload Supabase + `resetNonce` / toast de sucesso.
- `web-prototype/lib/products-api.ts`, `products-url.ts`, `actions/products.ts`, `api-prototype.ts`, `format.ts` — espelho lógico da raiz (`deleteProductSku` sem `redirect` no servidor; mensagens de sucesso alinhadas ao UX).

### Protótipo (Next na **raiz** do repositório — `npm run dev` → `:3000`)

- `app/products/page.tsx` — mesma composição que o protótipo (lista, filtros, detalhe, cadastro).
- `app/products/products-filters.tsx` (client + debounce + `ProductsPaginationBar` com salto de página), `product-selection-toast.tsx`, `products-table.tsx`, `product-detail-aside.tsx`, `product-lot-edit-form.tsx`, `product-lot-photo-form.tsx`, `product-sku-delete-form.tsx`, `product-markdown-hint.tsx`, `loading.tsx`.
- `app/products/new/new-product-form.tsx`, `new/page.tsx` — cadastro.
- `app/products/[id]/page.tsx` — redireciona para `/products?detail=<id>`.
- `app/products/actions.ts` — `revalidatePath` / refresh.
- `lib/products-api.ts`, `lib/products-url.ts`, `lib/product-attribute-presets.ts`, `lib/actions/products.ts`, `lib/actions/product-image-upload.ts`.
- `lib/api-prototype.ts` — cliente HTTP + cabeçalhos de actor (cookies + env + defaults em `next dev`).
- `lib/tenant.ts` — `resolveTenantId`, `resolveRole` (incl. `ALIEH_DEV_ROLE` e omissão em desenvolvimento).
- `lib/rbac.ts` — `requireAdmin` / `requireOperator` com `ALIEH_PROTOTYPE_OPEN`.
- `components/action-success-toast.tsx`, `components/form-status.tsx`, `components/product-image-upload.tsx`.
- `package.json` — scripts `dev`, `dev:api`, `dev:prototype`.
- `.env.example` — variáveis `API_PROTOTYPE_URL`, `API_PROTOTYPE_USER_ID`, notas de protótipo local.

### API

- `api-prototype/routes/products.py` — contratos HTTP espelhados por **ambas** as apps Next.

---

*Fim do relatório.*
