#!/usr/bin/env python3
"""Generate GitHub profile stat SVGs (stats.svg, languages.svg) into README_assets/.

Data comes from the GitHub GraphQL API using GITHUB_TOKEN (falls back to `gh auth token`).
No third-party rendering services — the SVGs are committed to the repository,
so they load for every visitor regardless of region or rate limits.
"""
import json
import os
import subprocess
import urllib.request
from datetime import date, datetime, timedelta, timezone

USER = os.environ.get("GITHUB_USERNAME", "JengasNX")
OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "README_assets"))

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(privacy: PUBLIC, ownerAffiliations: OWNER, first: 100) {
      totalCount
      nodes {
        stargazerCount
        primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
  }
}
"""


def gh_token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or ""
    if not tok:
        try:
            tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
        except FileNotFoundError:
            pass
    return tok


def graphql(token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt(n: int) -> str:
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


C = {
    "bg": "#1a1b27",
    "border": "#30334d",
    "title": "#68d5ed",
    "label": "#a9b1d6",
    "num": "#70a5fd",
    "bar_bg": "#252a41",
    "pct": "#bfe1f9",
}


def bytes_fmt(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f}MB"
    if n >= 1024:
        return f"{n / 1024:.0f}KB"
    return f"{n}B"


def activity_info(weeks: list) -> tuple:
    """(current_streak_days, last_active_date) из календаря контрибуций."""
    days = [d for w in weeks for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    last_active = None
    for d in reversed(days):
        if d["contributionCount"] > 0:
            last_active = date.fromisoformat(d["date"])
            break
    streak = 0
    if last_active is not None:
        today = date.today()
        # стрик считается живым, если последний вклад не старше вчерашнего дня
        if (today - last_active).days <= 1:
            streak = 1
            check = last_active
            by_date = {d["date"]: d["contributionCount"] for d in days}
            while True:
                prev = (check - timedelta(days=1)).isoformat()
                if by_date.get(prev, 0) > 0:
                    streak += 1
                    check = date.fromisoformat(prev)
                else:
                    break
    return streak, last_active


def rel_date(d) -> str:
    if d is None:
        return "—"
    diff = (date.today() - d).days
    if diff <= 0:
        return "Today"
    if diff == 1:
        return "Yesterday"
    return d.strftime("%b %d")


def stats_svg(d: dict) -> str:
    u = d["user"]
    cc = u["contributionsCollection"]
    commits = cc["contributionCalendar"]["totalContributions"] + cc["restrictedContributionsCount"]
    star_count = sum(r["stargazerCount"] for r in u["repositories"]["nodes"])
    code_size = sum(
        edge["size"] for r in u["repositories"]["nodes"] for edge in r["languages"]["edges"]
    )
    streak, last_active = activity_info(cc["contributionCalendar"]["weeks"])
    cells = [
        ("📊", "Commits (this year)", fmt(commits)),
        ("⭐", "Total Stars", fmt(star_count)),
        ("🔀", "Pull Requests", fmt(u["pullRequests"]["totalCount"])),
        ("🐛", "Issues", fmt(u["issues"]["totalCount"])),
        ("👥", "Followers", fmt(u["followers"]["totalCount"])),
        ("📦", "Public Repos", fmt(u["repositories"]["totalCount"])),
        ("💾", "Code Size", bytes_fmt(code_size)),
        ("🔥", "Current Streak", f"{streak}d" if streak else "0d"),
        ("⏱", "Last Activity", rel_date(last_active)),
    ]
    w, h, cw, rh = 540, 296, 168, 78
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="10" fill="{C["bg"]}" stroke="{C["border"]}" stroke-width="1"/>',
        f'<text x="24" y="38" font-family="Segoe UI,Roboto,sans-serif" font-size="15" fill="{C["title"]}" font-weight="600">'
        f'GitHub stats — {esc(USER)}</text>',
    ]
    for i, (icon, label, value) in enumerate(cells):
        col, row = i % 3, i // 3
        x = 24 + col * cw
        y = 72 + row * rh
        parts.append(f'<text x="{x}" y="{y}" font-family="Segoe UI,Roboto,sans-serif" font-size="17">{icon}</text>')
        parts.append(f'<text x="{x}" y="{y+28}" font-family="Segoe UI,Roboto,sans-serif" font-size="13" fill="{C["label"]}">{esc(label)}</text>')
        parts.append(f'<text x="{x}" y="{y+62}" font-family="Segoe UI,Roboto,sans-serif" font-size="24" fill="{C["num"]}" font-weight="700">{esc(value)}</text>')
        if col < 2:
            parts.append(f'<line x1="{x + cw - 28}" y1="{y - 26}" x2="{x + cw - 28}" y2="{y + 44}" stroke="{C["border"]}" stroke-width="1"/>')
    # нижний футер: время обновления (UTC)
    updated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    parts.append(f'<text x="{w-20}" y="{h-14}" text-anchor="end" font-family="Segoe UI,Roboto,sans-serif" font-size="11" fill="#6b7089">updated {updated}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def languages_svg(d: dict) -> str:
    u = d["user"]
    sizes, colors = {}, {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            sizes[name] = sizes.get(name, 0) + e["size"]
            if e["node"]["color"]:
                colors[name] = e["node"]["color"]
    total = sum(sizes.values())
    top = sorted(sizes.items(), key=lambda kv: -kv[1])[:7]
    if top:
        rows = len(top)
        w = 340
        h = 26 + rows * 34 + 10
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
            f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="10" fill="{C["bg"]}" stroke="{C["border"]}" stroke-width="1"/>',
            f'<text x="24" y="34" font-family="Segoe UI,Roboto,sans-serif" font-size="15" fill="{C["title"]}" font-weight="600">Most used languages</text>',
        ]
        for i, (name, size) in enumerate(top):
            pct = size / total * 100 if total else 0
            y = 52 + i * 34
            color = colors.get(name) or "#8b949e"
            parts.append(f'<rect x="24" y="{y}" width="10" height="10" rx="2" fill="{color}"/>')
            parts.append(f'<text x="42" y="{y+10}" font-family="Segoe UI,Roboto,sans-serif" font-size="13" fill="{C["label"]}">{esc(name)}</text>')
            parts.append(f'<text x="{w-24}" y="{y+10}" text-anchor="end" font-family="Segoe UI,Roboto,sans-serif" font-size="12" fill="{C["pct"]}">{pct:.1f}%</text>')
            parts.append(f'<rect x="24" y="{y+16}" width="{w-48}" height="6" rx="3" fill="{C["bar_bg"]}"/>')
            bw = max(3, int((w - 48) * size / total)) if total else 3
            parts.append(f'<rect x="24" y="{y+16}" width="{bw}" height="6" rx="3" fill="{color}"/>')
        updated = datetime.now(timezone.utc).strftime("%d %b %Y")
        parts.append(f'<text x="{w-20}" y="{h-8}" text-anchor="end" font-family="Segoe UI,Roboto,sans-serif" font-size="10" fill="#6b7089">updated {updated}</text>')
        parts.append("</svg>")
    else:
        w, h = 340, 90
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
            f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="10" fill="{C["bg"]}" stroke="{C["border"]}" stroke-width="1"/>',
            f'<text x="150" y="50" text-anchor="middle" font-family="Segoe UI,Roboto,sans-serif" font-size="14" fill="{C["label"]}">Публичного кода пока нет 🚀</text>',
            "</svg>",
        ]
    return "\n".join(parts)


def main() -> None:
    token = gh_token()
    if not token:
        raise SystemExit("No GITHUB_TOKEN / gh auth token")
    data = graphql(token)
    payload = data["data"]
    if not payload or data.get("errors"):
        raise SystemExit("GraphQL errors: " + json.dumps(data.get("errors", [])[:3]))
    os.makedirs(OUT_DIR, exist_ok=True)
    for filename, renderer in (("stats.svg", stats_svg), ("languages.svg", languages_svg)):
        with open(os.path.join(OUT_DIR, filename), "w", encoding="utf-8") as f:
            f.write(renderer(payload))
        print(f"wrote {filename}")


if __name__ == "__main__":
    main()
