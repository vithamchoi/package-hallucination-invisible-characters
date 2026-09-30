"""Mot lop goi LLM dung chung cho ca 4 bai, tu chuyen nha cung cap khi bi chan.

Vi sao can: khoa Groq mien phi tinh han muc token theo con so BAN XIN chu khong
theo con so ban DUNG. Mot model reasoning bat buoc max_tokens >= 1024 se dot het
han muc rat nhanh, va sau do moi request deu an 429. File .env cua du an co san
bon nha cung cap khac. Lop nay thu lan luot, nha nao con han muc thi dung.

Cach dung:

    from llm_providers import LLMPool
    pool = LLMPool(rpm=6, max_tokens=256)
    text, meta = pool.chat([{"role": "user", "content": "..."}])
    if text is None:
        ...  # meta["why"] noi vi sao

Thu tu uu tien co the doi bang bien moi truong LLM_ORDER, vi du:
    set LLM_ORDER=cerebras,groq,openrouter
"""
import json, os, time

import requests

# ----------------------------------------------------------------- cau hinh
# Moi muc: (ten, bien moi truong chua khoa, endpoint, model mac dinh)
# (ten, bien moi truong, endpoint chat, endpoint liet ke model, ten du phong)
#
# Ten model KHONG duoc doan. Lop nay goi /models de hoi tai khoan co gi, roi
# chon theo PREFER. Truong cuoi chi dung khi /models khong goi duoc.
PROVIDERS = [
    ("groq",       "GROQ_API_KEY",
     "https://api.groq.com/openai/v1/chat/completions",
     "https://api.groq.com/openai/v1/models",
     "openai/gpt-oss-20b"),
    ("cerebras",   "CEREBRAS_API_KEY",
     "https://api.cerebras.ai/v1/chat/completions",
     "https://api.cerebras.ai/v1/models",
     None),
    ("sambanova",  "SAMBANOVA_API_KEY",
     "https://api.sambanova.ai/v1/chat/completions",
     "https://api.sambanova.ai/v1/models",
     None),
    ("openrouter", "OPENROUTER_API_KEY",
     "https://openrouter.ai/api/v1/chat/completions",
     "https://openrouter.ai/api/v1/models",
     None),
    # Google cung cap endpoint tuong thich OpenAI, nen dung chung duoc mot ma.
    # Khoa GEMINI_API_KEY da nam san trong .env tu dau nhung chua ai dung.
    ("gemini",     "GEMINI_API_KEY",
     "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     "https://generativelanguage.googleapis.com/v1beta/openai/models",
     "gemini-2.5-flash"),
]

# Thu tu uu tien khi chon model. Model nho, khong reasoning, du sinh JSON ngan.
PREFER = [
    # Gemini 2.5 Flash dat truoc: goi mien phi rong nhat va nhanh nhat trong
    # so cac nha dang co khoa. "-lite" nhanh hon nua nhung yeu hon mot chut.
    "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest",
    "gemini-1.5-flash", "flash",
    "llama-3.3-70b", "llama-3.1-70b", "llama3.3-70b", "llama3.1-70b",
    "llama-3.1-8b", "llama3.1-8b", "llama-3.2-3b",
    "qwen-2.5-32b", "mixtral", "gemma2-9b", "gemma-3",
    "mistral",
]

# Khong dung cho viec nay: nhung model khong sinh van ban
SKIP = ("whisper", "tts", "embed", "guard", "vision", "image", "rerank",
        "moderation", "aqa")

# Model can max_tokens lon va reasoning_effort (khong tranh duoc thi moi dung)
REASONING_HINTS = ("gpt-oss", "qwen3", "deepseek-r1", "-r1",
                   "reasoning", "thinking", "o1-", "o3-")


def _is_reasoning(model_id: str) -> bool:
    m = (model_id or "").lower()
    return any(h in m for h in REASONING_HINTS)

# Nghi bao lau truoc khi thu lai mot nha cung cap vua bao 429 (giay)
COOLDOWN = float(os.getenv("LLM_COOLDOWN", "120"))


def load_dotenv(start=None):
    """Nap .env tim nguoc len cay thu muc. Khong ghi de bien da co."""
    here = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    for _ in range(6):
        p = os.path.join(here, ".env")
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
            return p
        nxt = os.path.dirname(here)
        if nxt == here:
            break
        here = nxt
    return None


class LLMPool:
    def __init__(self, rpm=6.0, max_tokens=256, temperature=0.3,
                 models=None, log=print, pin=True):
        """pin=True: CHON MOT model roi dung mai model do.

        Vi sao mac dinh la True. Trong ca bon bai nay, LLM chinh la HE THONG
        DANG DUOC DO. Neu giua chung doi sang nha khac, moi dong du lieu se
        den tu mot model khac nhau, va hieu ung ta muon do bi tron lan voi
        "model nao tra loi dong nay". Luc do so lieu khong con y nghia.

        Che do chuyen nha chi dung duoc khi LLM la CONG CU, khong phai doi
        tuong nghien cuu. Dat pin=False mot cach co y thuc neu dung vay.
        """
        load_dotenv()
        self.gap = 60.0 / float(rpm)
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self.log = log
        self.models = models or {}
        self._last_call = 0.0
        self._blocked_until = {}

        order = os.getenv("LLM_ORDER", "")
        names = [x.strip() for x in order.split(",") if x.strip()] if order else None

        self.free_only = os.getenv("LLM_FREE_ONLY", "1") != "0"
        self.pool = []
        for name, envk, url, list_url, fallback in PROVIDERS:
            if names and name not in names:
                continue
            key = os.getenv(envk)
            if not key:
                continue
            chosen = self.models.get(name) or self._discover(name, key, list_url, url)
            if not chosen:
                chosen = fallback
            if not chosen:
                self.log(f"  {name}: khong chon duoc model nao, bo qua")
                continue
            self.pool.append({"name": name, "key": key, "url": url,
                              "model": chosen,
                              "reasoning": _is_reasoning(chosen)})
        if names:
            self.pool.sort(key=lambda p: names.index(p["name"]))
        if not self.pool:
            raise SystemExit(
                "Khong tim thay khoa API nao trong .env. Can it nhat mot trong: "
                + ", ".join(e for _, e, _, _ in PROVIDERS))
        self.pin = pin
        for p in self.pool:
            tag = " [reasoning: max_tokens>=1024]" if p["reasoning"] else ""
            self.log(f"  {p['name']:11s} -> {p['model']}{tag}")
        if self.pin:
            self.pool = self.pool[:1]
            p = self.pool[0]
            self.log("")
            self.log(f"  GHIM MODEL: {p['name']} / {p['model']}")
            self.log("  Moi ban ghi se den tu dung model nay. Neu no hong,")
            self.log("  script DUNG LAI chu khong doi sang nha khac, vi doi model")
            self.log("  giua chung se lam hong thi nghiem.")

    def _discover(self, name, key, list_url, url_chat):
        """Hoi tai khoan co model gi, chon theo PREFER. None neu hoi khong duoc."""
        try:
            r = requests.get(list_url, timeout=30,
                             headers={"Authorization": f"Bearer {key}"})
            if r.status_code != 200:
                self.log(f"  {name}: /models HTTP {r.status_code}, dung ten du phong")
                return None
            ids = [m.get("id", "") for m in r.json().get("data", [])]
        except Exception as e:
            self.log(f"  {name}: /models loi {type(e).__name__}, dung ten du phong")
            return None
        if not ids:
            return None

        pool_ids = ids
        if name == "openrouter" and self.free_only:
            free = [i for i in ids if i.endswith(":free")]
            if free:
                pool_ids = free
            else:
                self.log("  openrouter: khong co ban :free nao, se dung ban TRA PHI")

        pool_ids = [i for i in pool_ids
                    if not any(sk in i.lower() for sk in SKIP)]

        # xep ung vien: uu tien khong-reasoning truoc
        order = []
        for want in PREFER:
            for i in pool_ids:
                if want in i.lower() and not _is_reasoning(i) and i not in order:
                    order.append(i)
        for i in pool_ids:
            if not _is_reasoning(i) and i not in order:
                order.append(i)
        for want in PREFER:
            for i in pool_ids:
                if want in i.lower() and i not in order:
                    order.append(i)
        for i in pool_ids:
            if i not in order:
                order.append(i)

        # Khong tin danh sach: GOI THU THAT mot lan. Day la cach paced_run.py
        # trong repo nay van lam, va no dung hon. Co model co trong /models
        # nhung goi vao thi 404 hoac tra ve content rong.
        for cand in order[:6]:
            ok, why = self._probe(name, key, url_chat, cand)
            if ok:
                return cand
            self.log(f"  {name}: loai {cand} -> {why}")
        return None

    def _probe(self, name, key, url_chat, model):
        """Goi that mot lan ngan, doi lai content khong rong."""
        body = {"model": model,
                "messages": [{"role": "user", "content": "Reply with the word OK."}],
                "temperature": 0.0,
                "max_tokens": 1024 if _is_reasoning(model) else 32}
        if _is_reasoning(model):
            body["reasoning_effort"] = "low"
        try:
            r = requests.post(url_chat, timeout=45, json=body,
                              headers={"Authorization": f"Bearer {key}"})
        except Exception as e:
            return False, f"{type(e).__name__}"
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:90]}"
        try:
            c = r.json()["choices"][0]["message"]["content"]
        except Exception:
            return False, "phan hoi la"
        return (True, "") if (c or "").strip() else (False, "content rong")

    # ------------------------------------------------------------------ noi bo
    def _pace(self):
        d = self.gap - (time.time() - self._last_call)
        if d > 0:
            time.sleep(d)

    def _available(self):
        now = time.time()
        return [p for p in self.pool if self._blocked_until.get(p["name"], 0) <= now]

    def _block(self, name, seconds):
        self._blocked_until[name] = time.time() + seconds

    # ------------------------------------------------------------------ cong khai
    def chat(self, messages, want_json=False, attempts_per_provider=2):
        """Tra ve (text, meta). text = None neu moi nha cung cap deu that bai."""
        tried = []
        for attempt in range(attempts_per_provider):
            avail = self._available()
            if not avail:
                # tat ca dang nghi: doi den khi nha gan nhat het nghi
                wait = min(self._blocked_until.values()) - time.time()
                if wait > 0:
                    self.log(f"    moi nha cung cap dang bi chan, doi {wait:.0f}s")
                    time.sleep(min(wait, 60))
                avail = self._available() or list(self.pool)
            for p in avail:
                if self.pin and p is not self.pool[0]:
                    continue
                self._pace()
                mt = max(1024, self.max_tokens) if p["reasoning"] else self.max_tokens
                body = {"model": p["model"], "messages": messages,
                        "temperature": self.temperature,
                        "max_tokens": mt}
                if p["reasoning"]:
                    body["reasoning_effort"] = "low"
                if p["name"] == "gemini":
                    # Gemini 2.5 mac dinh bat "thinking", dot them token va cham
                    # han. Tac vu o day chi la sinh mot JSON ngan nen tat di.
                    body["extra_body"] = {"google": {"thinking_config":
                                          {"thinking_budget": 0}}}
                if want_json:
                    body["response_format"] = {"type": "json_object"}
                try:
                    r = requests.post(p["url"], timeout=60, json=body,
                                      headers={"Authorization": f"Bearer {p['key']}"})
                    self._last_call = time.time()
                except Exception as e:
                    tried.append(f"{p['name']}:{type(e).__name__}")
                    self._block(p["name"], 30)
                    continue

                if r.status_code == 200:
                    try:
                        t = r.json()["choices"][0]["message"]["content"].strip()
                    except Exception:
                        tried.append(f"{p['name']}:body-la")
                        continue
                    if t:
                        return t, {"provider": p["name"], "model": p["model"],
                                   "tried": tried}
                    tried.append(f"{p['name']}:rong")
                    continue

                if r.status_code == 429:
                    ra = r.headers.get("retry-after")
                    cd = float(ra) if (ra or "").replace(".", "").isdigit() else COOLDOWN
                    tried.append(f"{p['name']}:429")
                    if self.pin:
                        # Ghim model thi phai CHO, khong duoc doi nha.
                        w = min(cd, 90)
                        self.log(f"    {p['name']} 429, cho {w:.0f}s (dang ghim model)")
                        time.sleep(w)
                    else:
                        self._block(p["name"], cd)
                        self.log(f"    {p['name']} 429, nghi {cd:.0f}s, chuyen nha khac")
                    continue

                if r.status_code in (400, 404):
                    # model sai ten hoac khong duoc phep: loai han trong phien nay
                    msg = r.text[:160]
                    self._block(p["name"], 10 ** 9)
                    tried.append(f"{p['name']}:{r.status_code}")
                    self.log(f"    {p['name']} HTTP {r.status_code}, bo qua han: {msg}")
                    continue

                tried.append(f"{p['name']}:{r.status_code}")
                self._block(p["name"], 30)
        return None, {"why": "moi nha cung cap deu that bai", "tried": tried}

    def chat_json(self, messages, attempts_per_provider=2):
        """Nhu chat() nhung ep ve dict. Tra ve (dict|None, meta)."""
        t, meta = self.chat(messages, want_json=True,
                            attempts_per_provider=attempts_per_provider)
        if t is None:
            return None, meta
        for fence in ("```json", "```"):
            if t.startswith(fence):
                t = t[len(fence):]
        if t.endswith("```"):
            t = t[:-3]
        try:
            return json.loads(t.strip()), meta
        except json.JSONDecodeError:
            meta["why"] = "khong phai JSON"
            return None, meta
