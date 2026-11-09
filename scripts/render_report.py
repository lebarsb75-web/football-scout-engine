import argparse
import html
import json
from pathlib import Path


def fmt(value, suffix=""):
    if value is None:
        return "—"
    return f"{value}{suffix}"


def main():
    parser = argparse.ArgumentParser(description="Render a Football Scout analysis JSON as HTML.")
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, default=Path("football-scout-report.html"))
    parser.add_argument("--player", default="Joueur analysé")
    parser.add_argument("--match", default="Match")
    args = parser.parse_args()

    data = json.loads(args.result.read_text(encoding="utf-8"))
    player = data.get("player", {})
    quality = data.get("quality", {})
    video = data.get("video", {})
    warnings = data.get("warnings", [])

    quality_label = quality.get("label", "unknown")
    verified_ball = quality.get("ball_metrics_reliable", False)
    distance = player.get("distance_meters_estimated")
    distance_display = fmt(round(distance / 1000, 2), " km") if distance is not None else "Non disponible"
    touches = fmt(player.get("ball_touches_estimated")) if verified_ball else "À vérifier"
    possession = fmt(player.get("possession_seconds_estimated"), " s") if verified_ball else "À vérifier"
    clips = player.get("touch_clip_windows_seconds", [])

    warning_html = "".join(f"<li>{html.escape(str(w))}</li>" for w in warnings)
    clip_html = "".join(
        f"<li>Action {i}: {start:.1f}s → {end:.1f}s</li>"
        for i, (start, end) in enumerate(clips, start=1)
    ) or "<li>Aucune fenêtre d'action disponible.</li>"

    report = f"""<!doctype html>
<html lang='fr'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Rapport Football Scout</title>
<style>
body{{font-family:Arial,sans-serif;background:#07100d;color:#f4f7f5;margin:0;padding:40px}}
.wrap{{max-width:1050px;margin:auto}}
header{{padding:28px;border:1px solid #24352e;border-radius:20px;background:#0e1915;margin-bottom:16px}}
.tag{{color:#59e391;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.12em}}
h1{{font-size:42px;margin:8px 0 4px}}p{{color:#a4b2ab;line-height:1.5}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.card{{padding:18px;border:1px solid #24352e;border-radius:16px;background:#0e1915}}
.card span{{display:block;color:#91a198;font-size:12px}}.card strong{{display:block;font-size:27px;margin-top:8px}}
section{{padding:22px;border:1px solid #24352e;border-radius:18px;background:#0e1915;margin-top:12px}}
.good{{color:#59e391}}ul{{color:#b6c1bb;line-height:1.7}}small{{color:#718078}}
@media(max-width:760px){{body{{padding:18px}}.grid{{grid-template-columns:1fr 1fr}}}}
</style>
</head>
<body><div class='wrap'>
<header><div class='tag'>Football Scout · Rapport individuel</div><h1>{html.escape(args.player)}</h1><p>{html.escape(args.match)} · vidéo {fmt(video.get('duration_seconds'), ' s')} · moteur {html.escape(str(data.get('engine_version','—')))}</p></header>
<div class='grid'>
<div class='card'><span>Qualité analyse</span><strong class='good'>{fmt(quality.get('score_percent'), '%')}</strong><small>{html.escape(str(quality_label))}</small></div>
<div class='card'><span>Suivi joueur</span><strong>{fmt(player.get('tracking_coverage_percent'), '%')}</strong><small>couverture estimée</small></div>
<div class='card'><span>Distance</span><strong>{distance_display}</strong><small>affichée seulement si calibrée</small></div>
<div class='card'><span>Touches</span><strong>{touches}</strong><small>{'gate qualité passée' if verified_ball else 'gate qualité non passée'}</small></div>
</div>
<section><div class='tag'>Possession</div><h2>{possession}</h2><p>Pourcentage du temps suivi : {fmt(player.get('possession_percent_of_tracked_time'), '%')}</p></section>
<section><div class='tag'>Séquences proposées</div><h2>{len(clips)} fenêtre(s)</h2><ul>{clip_html}</ul></section>
<section><div class='tag'>Contrôle qualité</div><ul>
<li>Visibilité ballon : {fmt(quality.get('ball_visibility_percent'), '%')}</li>
<li>Ré-identifications : {fmt(player.get('reidentifications'))}</li>
<li>Rejets d'identité : {fmt(player.get('identity_rejections'))}</li>
<li>Changements de plan détectés : {fmt(quality.get('scene_cuts_detected'))}</li>
<li>Sauts de tracking rejetés : {fmt(quality.get('rejected_tracking_jumps'))}</li>
</ul></section>
<section><div class='tag'>Avertissements techniques</div><ul>{warning_html}</ul></section>
</div></body></html>"""

    args.output.write_text(report, encoding="utf-8")
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
