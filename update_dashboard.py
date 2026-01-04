import datetime

path = "AI_Prediction_Engine.html"

with open(path, "r", encoding="utf-8") as f:
    html = f.read()

now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

marker = "Last Updated:"
if marker in html:
    start = html.index(marker) + len(marker)
    end = html.index("</p>", start)
    new_html = html[:start] + f" {now}" + html[end:]
else:
    new_html = html

with open(path, "w", encoding="utf-8") as f:
    f.write(new_html)
