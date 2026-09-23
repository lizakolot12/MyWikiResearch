# MyWikiResearch

Навичка для AI-агента [`wiki-interest`](wiki-interest/). Вона досліджує, як змінюється
інтерес до тем у різних мовних розділах Wikipedia, і робить графіки та PDF-звіти на одну
сторінку. Навичка допомагає вирішити, які теми розвивати і якими мовами запускати продукт.
Для кожного висновку вона показує, наскільки йому можна довіряти і чому.

Методологія, перевірка та план розвитку описані в [`wiki-interest/README.md`](wiki-interest/README.md).

## Встановлення

Готовий архів лежить у [Releases](https://github.com/lizakolot12/MyWikiResearch/releases):
файл `wiki-interest.zip`. Кожен реліз збирається автоматично й лише після того, як пройшли
тести. Навичці потрібен доступ до `wikimedia.org`, `*.wikipedia.org` і `www.wikidata.org`.

### Варіант 1: claude.ai

1. Завантажте `wiki-interest.zip` з останнього релізу.
2. У claude.ai відкрийте **Settings → Capabilities → Skills** і завантажте архів.

Навичка працює в пісочниці виконання коду claude.ai, тож доступна і в мобільних
застосунках. numpy і matplotlib там уже є. Доступ до `wikimedia.org` залежить від
мережевих налаштувань виконання коду у вашому акаунті.

### Варіант 2: Claude Code на комп'ютері

Потрібні **Python 3.10+** і [Claude Code](https://code.claude.com/docs).

**macOS / Linux:**
```bash
mkdir -p ~/.claude/skills && cd ~/.claude/skills
curl -LO https://github.com/lizakolot12/MyWikiResearch/releases/latest/download/wiki-interest.zip
unzip -o wiki-interest.zip && rm wiki-interest.zip
python3 wiki-interest/install.py --deps-only
```

**Windows (PowerShell):**
```powershell
$d = "$HOME\.claude\skills"; mkdir $d -Force | Out-Null
Invoke-WebRequest https://github.com/lizakolot12/MyWikiResearch/releases/latest/download/wiki-interest.zip -OutFile "$d\wiki-interest.zip"
Expand-Archive "$d\wiki-interest.zip" $d -Force; Remove-Item "$d\wiki-interest.zip"
python "$d\wiki-interest\install.py" --deps-only
```

`install.py --deps-only` створює в теці навички `.venv` з numpy і matplotlib (системний
Python не змінюється) і запускає `doctor`. Наприкінці має бути `"pageviews_api": "ok"` і
`"wikidata_api": "ok"`.

**Оновлення:** виконайте ті самі команди ще раз. Код навички оновиться, а завантажені
раніше дані (`.cache`) і `.venv` збережуться.

## Запуск

```bash
mkdir -p ~/wiki-research && cd ~/wiki-research
claude --model haiku
```

Графіки й PDF-звіти з'являються в теці, з якої запущено Claude Code, у підтеці
`wiki-interest-output/`.

## Як переконатися, що навичка працює

1. **Claude бачить навичку.** Наберіть у Claude Code `/` і знайдіть у списку `wiki-interest`.
2. **Поставте питання.** Щоб навичка точно спрацювала, почніть повідомлення з `/wiki-interest`:
   ```
   /wiki-interest Ми думаємо додати курс з астрономії до освітнього застосунку. Чи зростає інтерес до цієї теми в україномовній Wikipedia, і наскільки цьому зростанню можна довіряти?
   ```
   Можна писати й без `/wiki-interest`. Тоді агент сам вирішує, чи використати навичку,
   за її описом.
3. **Агент викликає скрипт навички.** У стрічці дій має бути команда на кшталт
   `python …/wiki-interest/scripts/wiki_interest.py analyze --topics "Astronomy" --langs uk`.
   Коли Claude попросить дозволу її виконати, дозвольте.
4. **У відповіді є:**
   - вердикт («зростає», «повільно зростає», «стабільний»…) і тренд у відсотках на рік;
   - рівень довіри до висновку з причинами;
   - застереження, що перегляди Вікіпедії показують інтерес, а не готовність платити;
   - шлях до графіка.
5. **Уточнення працюють у тій самій розмові.** Спробуйте «Додай польську і чеську» (дані
   беруться з кешу, тож відповідь буде швидшою) або «Зроби PDF-звіт».

Перевірити сам скрипт, без агента:
```bash
S=~/.claude/skills/wiki-interest/scripts/wiki_interest.py
python3 $S doctor
python3 $S analyze --topics "Astronomy" --langs uk,pl --months 24
python3 $S report --title "Тест" --summary "Перевірка" --rec "Перевірка" --out test.pdf
```

## Якщо щось не так

| Проблема | Що зробити |
|---|---|
| `wiki-interest` немає у списку `/` | перевірте, що є файл `~/.claude/skills/wiki-interest/SKILL.md`, і перезапустіть Claude Code |
| `doctor` показує `api_error` | немає доступу до `wikimedia.org`: перевірте мережу, VPN або проксі |
| `CERTIFICATE_VERIFY_FAILED` | Python без сертифікатів (буває на macOS): запустіть `Install Certificates.command` з теки Python або `pip install certifi` у `.venv` навички |
| агент пише власний код або шукає в інтернеті | почніть повідомлення з `/wiki-interest` |
| `missing Python package` | запустіть `install.py --deps-only` ще раз |

## Для розробки

Клон репозиторію і встановлення з нього:
```bash
git clone https://github.com/lizakolot12/MyWikiResearch.git
cd MyWikiResearch
./setup.sh              # Windows: setup.cmd; копія в ~/.claude/skills + .venv + doctor
./setup.sh --link       # посилання замість копії: зміни в репозиторії діють одразу
./setup.sh claude haiku # встановити й одразу відкрити Claude Code на Haiku
```
`setup.sh` передає параметри в `wiki-interest/install.py` (`--project DIR`, `--dest DIR`,
`--zip FILE`, `--no-doctor`; повний список: `./setup.sh --help`).

Тести й evals:
```bash
cd wiki-interest
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest -q tests                                       # офлайн, на фейковому API
python evals/run_evals.py --model claude-haiku-4-5-20251001     # агент на справжньому API
```

Новий реліз: `git tag v1.0.0 && git push origin v1.0.0`. Workflow
`.github/workflows/release.yml` запустить тести, збере `wiki-interest.zip` тим самим
`install.py --zip` і прикріпить архів до релізу.
