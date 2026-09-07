# Runbook: API retorna HTTP 500 por permissão de escrita em `storage/`

> Procedimento de contorno. Aplicar sempre que a API responder 500 após subir a stack.
> Análise da causa-raiz: [`BUG-NO-SETUP.md`](BUG-NO-SETUP.md).
> Última recorrência registrada: 2026-09-07 (rota `/brands`, durante execução do Locust).

---

## 1. Como reconhecer

Sintoma típico — uma ou mais rotas retornam 500 enquanto outras seguem 200:

```
GET /status     -> 200
GET /products   -> 200
GET /brands     -> 500
```

Do lado do Locust, aparece como falha de carga do catálogo:

```
ERROR/common.catalog: Falha ao carregar catalogo de http://localhost:8091:
500 Server Error: Internal Server Error for url: http://localhost:8091/brands
```

Mensagem enganosa: sugere que a stack está fora do ar. Ela está no ar — os containers estão `Up`.

## 2. Como confirmar

```bash
docker exec pst-laravel-api-1 tail -5 storage/logs/laravel.log
```

Assinatura do defeito:

```
file_put_contents(/var/www/storage/framework/cache/data/c9/4c/c94c1f04...):
Failed to open stream: Permission denied
```

Confirmação da divergência de uid:

```bash
docker exec pst-laravel-api-1 id
# uid=1000(www-data) gid=82(www-data)   <- processo php-fpm

docker exec pst-laravel-api-1 ls -ld /var/www/storage/framework/cache/data/*/*
# drwxr-xr-x 82 www-data ...            <- dono 82, grupo sem write
```

Dono é 82, processo é 1000, grupo só tem `r-x`. Sem permissão de escrita.

## 3. Correção (aplicar)

```bash
docker exec -u root pst-laravel-api-1 sh -c \
  'rm -rf /var/www/storage/framework/cache/data/* && \
   chmod -R 777 /var/www/storage /var/www/bootstrap/cache'
```

Variante mínima, sem limpar o cache (suficiente na maioria dos casos, pois o gid 82
é o mesmo nas duas imagens — só o uid diverge):

```bash
docker compose exec -u 0 laravel-api sh -c \
  'chmod -R g+w /var/www/storage /var/www/bootstrap/cache'
```

O `rm -rf` do cache é recomendável quando a rota afetada usa `Cache::remember`: remove
entradas antigas gravadas com dono/modo errado, e o php-fpm recria como dono.

## 4. Verificação

```bash
for p in /status /brands /categories /categories/tree /products; do
  printf "%-20s %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8091$p)"
done
```

Esperado: todas 200.

Smoke test com o Locust (a partir de `locust/`, com o venv ativo):

```bash
locust --users 5 --run-time 20s --autostart --headless
```

Esperado: `0(0.00%)` de falhas na linha `Aggregated`.

## 5. Por que volta a acontecer

O serviço `composer` está no `docker-compose.yml` **base**, portanto executa a cada
`docker compose up`, e roda `chown -R www-data /var/www` resolvido dentro da imagem
`composer:2.6.6`, onde `www-data` é **uid 82**. O php-fpm roda como **uid 1000**.
Detalhamento completo em [`BUG-NO-SETUP.md`](BUG-NO-SETUP.md), seções 2 e 5 — a
recorrência de 2026-09-07 que originou este runbook está na seção 5.1.

Consequência prática: **reaplicar o comando da seção 3 após cada `docker compose up`.**
`docker compose down -v` não resolve — reintroduz o defeito.

## 6. Correção definitiva (ainda não aplicada)

Em `practice-software-testing/docker-compose.yml:53`, trocar:

```yaml
command: -c "composer install ... && chown -R www-data /var/www && chmod 777 /var/www"
```

por `chown -R 1000:82 /var/www`. Elimina a ambiguidade do nome `www-data` entre as duas
imagens. Alternativas avaliadas na seção 7 do `BUG-NO-SETUP.md`.

## 7. Impacto sobre os testes

Falso positivo de origem ambiental: qualquer suíte executada com a permissão quebrada
acusa falha sem que exista defeito na aplicação. Rodar a verificação da seção 4 **antes**
de qualquer execução de carga, e descartar resultados de execuções que começaram com 500.
