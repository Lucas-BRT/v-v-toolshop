# Defeito de ambiente: `/products` retorna HTTP 500 após `docker compose up`

> Registro para análise posterior. Trabalho de V&V.
> Data da investigação: 2026-09-05
> Commit da base: `9e7736c3` (branch `main`)
> Sprint sob teste: `sprint5` (`SPRINT=sprint5` no `.env`)
> Procedimento operacional de contorno: [`FIX-PERMISSOES.md`](FIX-PERMISSOES.md)

---

## 1. Sintoma

Após subir o ambiente com `docker compose up -d`, a listagem de produtos não carrega
na UI (`http://localhost:4200`). A chamada correspondente à API falha:

```
GET   http://localhost:8091/products  -> 500   (corpo vazio)
QUERY http://localhost:8091/products  -> 500   (corpo vazio)
GET   http://localhost:8091/status    -> 200
```

Todos os containers sobem e permanecem `Up`. O banco está populado corretamente
(53 produtos, 2 marcas, 4 usuários). O erro **não** aparecia em
`storage/logs/laravel.log`.

## 2. Causa-raiz

Divergência de UID do usuário `www-data` entre duas imagens do mesmo `docker-compose.yml`,
atuando sobre o mesmo bind mount (`./sprint5/API:/var/www`).

| Imagem | Serviço | `www-data` |
|---|---|---|
| `composer:2.6.6` (Alpine) | `composer` | **uid 82**, gid 82 |
| build de `_docker/api.docker` | `laravel-api` (php-fpm) | **uid 1000**, gid 82 |

`docker-compose.yml:53`:

```yaml
command: -c "composer install --no-dev --optimize-autoloader --ignore-platform-req=ext-ffi && chown -R www-data /var/www && chmod 777 /var/www"
```

O `chown -R www-data` é resolvido **dentro da imagem `composer`**, ou seja, para o uid 82 —
que não é o uid sob o qual o php-fpm executa (1000).

### Sequência da falha

1. php-fpm (uid 1000, umask 022) cria os diretórios de cache de arquivo, por exemplo
   `storage/framework/cache/data/60/60/`, com modo **755** e dono **1000**.
   Escreve normalmente, pois é o dono.
2. O serviço `composer` — presente no `docker-compose.yml` **base**, portanto executado a
   **cada `up`** — roda `chown -R www-data /var/www`, alterando o dono para **82**.
3. php-fpm deixa de ser dono desses diretórios. Passa a valer a permissão de grupo (`r-x`).
   Perde o direito de escrita.
4. `ProductService::index()` (`sprint5/API/app/Services/ProductService.php:49`) usa
   `Cache::remember(...)` com `CACHE_DRIVER=file`. A gravação falha:

```
local.ERROR: file_put_contents(/var/www/storage/framework/cache/data/60/60/6060209c...):
Failed to open stream: Permission denied
  at /var/www/vendor/laravel/framework/src/Illuminate/Filesystem/Filesystem.php:204
```

5. Resposta 500. `/status` continua 200 porque não escreve cache nem log — daí a
   impressão inicial de que "só produtos" estava quebrado.

## 3. Falha de mascaramento (achado secundário)

O mesmo problema de permissão atingia `storage/logs/laravel.log`. Consequência:

1. O controller chama `Log::debug(...)`.
2. Monolog `StreamHandler` lança `UnexpectedValueException: The stream or file ... could not be opened`.
3. O exception handler do Laravel tenta **registrar esse erro em log** — e falha novamente.
4. Resultado: HTTP 500 com **corpo vazio e nenhum registro em log**, mesmo com `APP_DEBUG=true`.

O erro primário (cache) só se tornou visível depois de destravar a escrita do log.

Relevância para V&V: é um defeito de **observabilidade / diagnosticabilidade**. Uma falha
sem sinal diagnosticável eleva de forma direta o custo da atividade de verificação.

## 4. Hipótese descartada

Primeira hipótese: o serviço `cron` (definido em `docker-compose.override.yml`) executa como
`uid=0(root)` e estaria criando arquivos inacessíveis ao php-fpm.

**Refutada por evidência.** Nenhum arquivo pertencente a root sob o bind mount:

```
$ docker exec pst-laravel-api-1 find /var/www/storage -user 0
(sem resultado)
```

Todos os arquivos pertenciam ao uid 82 — assinatura do `chown` do serviço `composer`,
não do cron.

## 5. Reprodutibilidade

Reproduz de forma determinística. Verificado que `docker compose down -v` seguido de
`docker compose up -d` **reintroduz** o defeito, pois o serviço `composer` está no arquivo
base e executa em toda subida. Recriar o ambiente do zero reproduz o problema em vez de
corrigi-lo.

Também verificado que `docker compose -f docker-compose.yml up -d` (sem o override) **não**
remove o container `cron` já existente — ele apenas deixa de ser gerenciado e continua em
execução como container órfão. Irrelevante para este defeito, mas registrado por ter sido
testado durante a investigação.

### 5.1 Recorrência observada — 2026-09-07

O defeito voltou a se manifestar, agora em **rota diferente**: `GET /brands` retornando 500
enquanto `/products`, `/categories` e `/status` respondiam 200. Detectado durante execução
do Locust, que aborta o carregamento do catálogo:

```
ERROR/common.catalog: Falha ao carregar catalogo de http://localhost:8091:
500 Server Error: Internal Server Error for url: http://localhost:8091/brands
```

Mesma causa-raiz, mesma assinatura no log:

```
local.CRITICAL: Unhandled Exception {"exception":"ErrorException","message":
"file_put_contents(/var/www/storage/framework/cache/data/c9/4c/c94c1f04...):
Failed to open stream: Permission denied","route":"brands","method":"GET"}
```

Confirmado: `data/c9/4c` estava `drwxr-xr-x` dono **82**, com php-fpm em uid **1000**.

Duas observações relevantes:

1. **A rota afetada varia conforme quais entradas de cache já existem em disco.** Em
   2026-09-05 foi `/products` (`ProductService::index()`); em 2026-09-07 foi `/brands`
   (`BrandService::getAllBrands()`, `app/Services/BrandService.php:17`, chave `brands.all`,
   TTL 3600s). Os diretórios de primeiro nível sob `data/` estavam com escrita de grupo,
   então parte das rotas seguia funcionando — apenas os subdiretórios de segundo nível
   herdados do `chown` anterior é que bloqueavam. Isso mascara o diagnóstico: o sintoma
   parece específico de uma rota, mas o defeito é do ambiente.
2. **Nesta recorrência o log estava gravável**, ao contrário de 2026-09-05 (seção 3).
   Por isso o erro apareceu em `storage/logs/laravel.log` de imediato, sem a etapa extra
   de destravar a escrita do log.

Reforça a conclusão da seção 5: o contorno é volátil e precisa ser reaplicado, e nenhuma
execução de teste deve começar sem a verificação de smoke.

## 6. Contorno aplicado

```bash
docker compose exec -u 0 laravel-api sh -c \
  'chmod -R g+w /var/www/storage /var/www/bootstrap/cache'
```

Funciona porque o **gid é 82 em ambas as imagens** — apenas o uid diverge. Concedida a
escrita ao grupo, o uid 1000 volta a escrever independentemente do dono.

Verificação pós-contorno:

```
GET   /products -> 200
QUERY /products -> 200
```

**Paliativo, não corretivo.** Precisa ser reaplicado após cada `docker compose up`.

Variante aplicada na recorrência de 2026-09-07, que além da permissão descarta as entradas
de cache gravadas com dono errado (o php-fpm as recria como dono):

```bash
docker exec -u root pst-laravel-api-1 sh -c \
  'rm -rf /var/www/storage/framework/cache/data/* && \
   chmod -R 777 /var/www/storage /var/www/bootstrap/cache'
```

Verificação pós-contorno (2026-09-07): `/brands`, `/categories`, `/categories/tree`,
`/products`, `/products/search` e `/status` em 200; Locust com 5 usuários por 20s,
40 requisições, `0(0.00%)` de falhas.

## 7. Correções definitivas possíveis

| # | Correção | Observação |
|---|---|---|
| 1 | Em `docker-compose.yml:53`, trocar `chown -R www-data` por `chown -R 1000:82` | Elimina a ambiguidade do nome entre imagens. Corrige na origem. |
| 2 | `CACHE_DRIVER=database` no `.env` da API | As tabelas `cache` e `cache_locks` já existem no schema. Tira o cache do sistema de arquivos, mas não resolve sessões nem views compiladas. |
| 3 | Alinhar o `www-data` da imagem `api.docker` ao uid 82 | Mais invasivo; afeta a correspondência de uid com o usuário do host. |

Preferência: opção 1. Ataca a causa-raiz com uma linha e não altera o comportamento
da aplicação.

## 8. Classificação para o relatório

| Campo | Valor |
|---|---|
| Tipo | Defeito de configuração / infraestrutura |
| Fase de origem | Configuração do ambiente (não codificação) |
| Detectado por | Teste exploratório de smoke no ambiente |
| Severidade | Alta — bloqueia funcionalidade central da aplicação |
| Escopo | Ambiente local Docker; **não** é defeito da lógica da aplicação |
| Achado associado | Observabilidade: falha sem diagnóstico (seção 3) |

Não é falha de **validação** (produto construído não corresponde à necessidade) nem de
**verificação** da aplicação (código não corresponde à especificação). É defeito no
ambiente de execução, e deve ser relatado separadamente dos defeitos plantados em
`sprint5-with-bugs`.

Constitui **ameaça à validade** de qualquer suíte automatizada executada contra este
ambiente: testes sobre `/products` acusariam falha sem que exista defeito na aplicação —
falso positivo de origem ambiental.

## 9. Evidências coletadas

```
$ docker run --rm --entrypoint sh composer:2.6.6 -c 'id www-data'
uid=82(www-data) gid=82(www-data) groups=82(www-data),82(www-data)

$ docker exec pst-laravel-api-1 id www-data
uid=1000(www-data) gid=82(www-data) groups=82(www-data),82(www-data)

$ docker exec pst-laravel-api-1 ls -ld /var/www/storage/framework/cache/data/60/60
drwxr-xr-x  2  82  www-data  4096  /var/www/storage/framework/cache/data/60/60

$ docker exec pst-mariadb-1 mysql -uroot -proot -e "use toolshop; select count(*) from products;"
53
```
