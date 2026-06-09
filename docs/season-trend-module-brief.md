# Design brief: "This season vs last" trend module

**Product:** Fever Watch (PharmEasy) - a daily, consumer-facing monsoon-fever risk indicator for ~228 Indian cities.
**Component:** A per-city "this monsoon vs last monsoon" weekly trend module, shown on each city page.
**Prepared:** 8 Jun 2026
**For:** Design mocks.

---

## 1. Overview

Fever Watch gives each Indian city one daily **risk score (0-100)** for the top monsoon fevers (dengue, malaria, chikungunya, typhoid, viral fever), blended from three signals: breeding **weather**, Google **search** interest, and PharmEasy **lab** positivity.

This module adds a **season-over-season trend**: how this monsoon (1 Jun - 30 Oct) is tracking **versus the same weeks last year**, week by week. A layman should grasp "are we better or worse than last year?" in one glance; the curious can dig into the three underlying signals.

It is a **risk indicator, not a diagnosis or a case count.** The design must feel calm, friendly, and trustworthy, never like a clinical analytics dashboard.

## 2. Audience & goals

- **Audience:** general consumers in India, non-experts, mostly on mobile.
- **Primary goal:** an instant, plain-language verdict - above / below / in line with last year, rising / falling.
- **Secondary goal:** optional depth - the three signals over the season, for the curious.
- **Design tension to solve:** four metrics x two series (this year vs last) x ~22 weeks is a lot of data. It must NOT feel heavy. The brief's core idea is **words first, one chart at a time, progressive disclosure.**

## 3. Brand & visual system

- **Type:** Inter.
- **Brand:** Porcelain Green `#10847E`; gold accent `#EFD06C`.
- **Risk ramp (used only for the "Overall" metric):** LOW `#2FA66F`, LOW-MODERATE `#C7A93C`, MODERATE `#E8923A`, HIGH `#E4572E`.
- **Signal colors:** Weather teal `#15ACA5`, Search purple `#7C6CD6`, Labs blue `#3661B0`.
- Card-based UI, rounded corners (~16-20px), soft shadows; generous white space.
- Co-branded with PharmEasy (Inter wordmark lockup in the page header; this module is one card within the page).

## 4. Component anatomy (top to bottom)

```
+--------------------------------------------------+
|  This monsoon vs last in {City}                  |  <- section title
|  v Tracking BELOW last year        [ -12% chip ] |  <- VERDICT (plain language) + delta chip
|  Last year peaked at 71 (HIGH) in late August.   |  <- supporting context line
|                                                  |
|  [ Overall ]   Weather   Searches   Labs         |  <- segmented tabs (ONE chart at a time)
|                                                  |
|  +-- chart -----------------------------------+  |
|  |  this year   = bold colored line           |  |
|  |  last year   = soft gray band ("normal")   |  |
|  |  (o) "you are here" dot at current week     |  |
|  |  future weeks left blank (season ongoing)   |  |
|  |  Jun . Jul . Aug . Sep . Oct  (x ticks)     |  |
|  +---------------------------------------------+  |
|  "Risk is easing as rainfall tapers."            |  <- one-line caption (takeaway in words)
|  Sources: NASA POWER . Google Trends . PharmEasy |  <- tiny provenance microcopy
+--------------------------------------------------+
```

**Element list:**
1. Section title.
2. **Verdict line** - the plain-language headline (above / below / in line; rising / falling).
3. **Delta chip** - this year vs last (e.g. `-12%`) with direction.
4. Supporting context line (e.g. last year's peak value, band, and rough timing).
5. **Metric tabs / segmented control** - Overall (default), Weather, Searches, Labs.
6. **Chart** - one at a time (see anatomy above).
7. **Caption** - one sentence restating the takeaway for the selected metric.
8. Provenance microcopy.
9. Optional collapse/expand affordance ("See the full season trend").

## 5. The four metric tabs

| Tab | Line color | What it shows (layman framing) | Background |
|---|---|---|---|
| **Overall** (default) | risk ramp | "your headline risk vs last year" | faint LOW / MODERATE / HIGH color zones = the implied y-axis |
| **Weather** | teal `#15ACA5` | "breeding conditions - leads weeks ahead" | none (plain 0-100) |
| **Searches** | purple `#7C6CD6` | "public concern" | none |
| **Labs** | blue `#3661B0` | "confirmed positivity - lagging" | none |

Default view is **Overall, expanded**; signal tabs are one tap away.

## 6. Design principles (this is what keeps it light)

1. **Words first.** The verdict sentence + chip IS the answer; the chart is supporting evidence.
2. **One chart at a time** via tabs - never four dual-line charts on screen at once.
3. **Last year = soft gray band; this year = one bold line.** The whole reading becomes "is the bold line above or below the gray?"
4. **No numeric y-axis, no gridlines.** Month ticks only. For Overall, the colored risk zones replace the axis.
5. **Honest about "in progress":** the this-year line stops at the current week with a "you are here" dot; do not draw a full season that has not happened yet.
6. **Progressive disclosure:** the whole block can sit behind a "See the full season trend" collapse so the page stays calm for people who only want today's number.
7. **Thin, minimal chart chrome** - this will ship as lightweight inline SVG, so avoid dense, library-style axes, legends, and tick clutter. Lots of breathing room.

## 7. States & variants to mock

1. **Collapsed default** - verdict + chip only (calm entry state).
2. **Overall expanded** (the hero state).
3. **Signal tab selected** (e.g. Weather) - note the signal color and no risk zones.
4. **Tooltip / tap on a week** - exact-value bubble, e.g. "Week of 12 Aug - This year 58 - Last year 66".
5. **Early-season** - the this-year line is only 1-2 points near June (very short), gray "last year" band full.
6. **Labs not yet available** - an empty / "coming soon" state for the Labs tab (lab history may not exist for some cities).
7. **Verdict variants** - above / below / in line; rising / falling / steady (see copy in section 9).
8. **Mobile and desktop** layouts (see section 8).

## 8. Responsive behaviour

- **Mobile (primary):** strictly the tabbed single chart. Order: verdict -> tabs -> one chart -> caption. No more than one chart visible.
- **Desktop:** the **Overall** chart can be the hero (large), with the three signal charts shown as a **small-multiples grid** (mini "this-vs-last" sparklines, click to enlarge). Glanceable overview without clutter.

## 9. Realistic sample content (use this so mocks feel real)

**Sample city:** Pune. **Range:** weekly, 1 Jun - 30 Oct = ~22 points. **Scale:** 0-100.

- **This year (partial, line ends at "now"):** Jun 22 -> Jul 35 -> early Aug 48 -> current ~52.
- **Last year (full season):** Jun 30 -> Jul 52 -> peaks **71 in late Aug** -> falls to ~40 by late Oct.

**Verdict copy variants:**
- Below: "Tracking **below** last year so far - down 12%"
- Above: "Running **higher** than last year - up 9%, and rising"
- In line: "About the **same** as last year so far"

**Caption examples (one per metric):**
- Overall: "Risk is easing as rainfall tapers."
- Weather: "Breeding conditions peaked earlier than last year."
- Searches: "Public concern is below last August's spike."
- Labs: "Positivity is tracking last year closely."

## 10. Constraints & guardrails

- Must read as **lightweight and friendly**, never a clinical dashboard.
- It is a risk **indicator**, not case counts or a diagnosis. Weather temperature is not body-temperature fever.
- Lab data is shown only as an **aggregate trend**, never anything re-identifiable.
- Copy uses plain ASCII hyphens only (no em dashes, en dashes, or middot separators).
- Will be built as **hand-rolled inline SVG** (no charting library), so keep visuals simple, thin-lined, and minimal-chrome.

## 11. Deliverables requested from design

Mocks (mobile + desktop) for:
1. Collapsed default (verdict + chip).
2. Overall expanded (hero) - mobile and desktop.
3. A signal tab selected (e.g. Weather).
4. Tooltip / tap state.
5. Early-season state.
6. Labs "coming soon" empty state.
7. Desktop small-multiples (all-four-at-a-glance) layout.
8. The verdict line in 3 variants (above / below / in line).

A component/spec sheet (spacing, type scale, colors, line weights, chip and tab styles) would be ideal for handoff.

---

## Appendix: data shape (for realistic mocks)

Per city, the module is driven by a compact weekly series:

```
{
  "city": "pune",
  "weeks": ["2025-06-02", "2025-06-09", ... "2025-10-27"],   // ~22 week-start dates
  "lastYear": {
    "overall":  [30, 33, ... 71 ... 40],   // 0-100, full season
    "weather":  [...],
    "search":   [...],
    "labs":     [...]
  },
  "thisYear": {                              // partial - ends at the current week
    "overall":  [22, 35, 48, 52],
    "weather":  [...],
    "search":   [...],
    "labs":     [...]                        // may be empty if lab history is unavailable
  },
  "asOfWeekIndex": 3                          // position of the "you are here" marker
}
```

Each series is 0-100. "This year" is partial (season in progress); "last year" is the full 1 Jun - 30 Oct window.
