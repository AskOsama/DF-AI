# Digital Forensics Data & AI (DF-AI)

A bilingual (English / Arabic) static course website on **processing digital-forensic data with
artificial intelligence** — lawfully, admissibly, and in-house. Prepared by Dr. Osama Almurshed.

## The five parts

1. **Foundations** — data science studies the data, AI is the algorithms that handle it, digital
   forensics is the evidence-grade data we analyse.
2. **The Data** — generation, location, lifecycle, the order of volatility, the four ownership
   layers (host / network / ISP-telco / cloud), and lawful acquisition from third parties.
3. **Admissibility, Privacy, Security & De-anonymization** — when evidence is admissible, building
   tracing tools that respect privacy policies, your own operational security, de-identification and
   the linkage attack that re-identifies "anonymous" data.
4. **Building In-House AI Tools (Beyond ML)** — constraint satisfaction, optimization, machine
   learning, knowledge reasoning, topic modelling and search, all runnable locally.
5. **Agentic Solutions** — the reasoning loop and ReAct, the eight agent patterns, where forensics
   sits on the cross-domain map, open-source frameworks, and the anatomy of a forensic triage agent.

## Structure

```
index.html / index_ar.html      Landing page (EN + Arabic RTL)
modules/part1..part5.html        English module pages
modules/part1..part5_ar.html     Arabic RTL twins
demos/                           Self-contained interactive demos (vanilla JS)
css/                             landing.css (editorial, forensic teal/gold retint),
                                 styles.css (demo base), demo-polish.css
js/                              drawing-tool + AI strategy engines
images/diagrams/                 (reserved; diagrams are inline SVG in the pages)
```

No build step, no framework — static HTML + custom CSS + vanilla JavaScript, Google Fonts via CDN.

## Opening the site

**Just open `index.html` in any browser — double-click it.** That's it. The site is 100% static,
client-side HTML/CSS/JS: **no server, no build step, no install.** It runs straight from the
`file://` protocol. The only thing that touches the network is the Google Fonts stylesheet; with no
internet the layout simply falls back to system fonts and everything else still works offline from
the local files.

Every relative link and the EN⇄AR language switcher work the same way over `file://` as they would
on a web host.

## Demos

Each file in `demos/` is self-contained and opens directly by double-click, no server needed. Highlights:
`deanonymization_demo` (the Sweeney linkage attack, animated), `forensic_process_demo` (six-step
investigation), `entropy_calculator_demo`, `privacy_budget_tracker`, and the Part-4 AI demos
(`heuristic_demo`, `objective_function_demo`, `ml-viz-v2`, `classification_demo`,
`activation_functions_demo`, `family_inference_demo`). Arabic twins exist where the source provided
them (`*_ar.html`); the others fall back to English.

## Credits & license

Materials are licensed under **CC BY 4.0**. Attribution: "DF-AI Course Materials, licensed under
CC BY 4.0." Privacy case studies adapted from open de-identification materials; agent patterns
adapted from an open survey of agent architectures.
