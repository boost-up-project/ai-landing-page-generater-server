# Persona-based UX personalization rules

Use this operational decision layer before selecting component order, layout, copy, or
images. Brand and Campaign contexts define truth, mandatory information, available
offers, and permitted actions. Persona data may change relevance, priority, expression,
and delivery, but must never change those facts.

## 1. Interpret signals before changing UI

Do not map raw persona attributes directly to components. For each persona, first create
`ux_strategy` through this sequence:

`persona data → supported signal → UX decision → page strategy → supplied component`

Each core category owns only its UX area:

- profile → expression/readability; never infer taste, income, interests, or intent
- situation → current context and usage scenario; never select a product from household
  type alone
- needs → desired value and primary benefit
- pain_points → current problem and opening problem framing
- interests → supporting content topics, only when Campaign content supports them
- behaviors → exploration, comparison, recommendation, detail, and interaction strategy
- appendix.purchase_journey → CTA readiness and action intensity only
- appendix.dislikes → exclusion of optional content/style only

## 2. Evidence and safe defaults

- Explicit persona statements have highest authority.
- A derived signal is allowed only when it is direct, conservative, necessary for a UX
  decision, and cannot reasonably mean multiple things.
- Never derive interests, behavior, purchasing power, or purchase stage from demographics.
- Never derive purchase stage from situation or behavior.
- A dislike is not evidence of the opposite preference.
- Missing/uncertain evidence means preserve the Campaign default for that decision area.
- Sparse persona data produces partial personalization, never invented completion.

## 3. Select the page strategy

Choose one campaign-relevant `primary_problem` from pain_points and one
`primary_value` from needs. Rank candidates by campaign relevance, explicit importance,
recurrence, and specificity. Do not invent a problem when none is supported.

Hero direction:

1. Campaign truth and objective
2. primary_problem, when supported
3. primary_value, when supported
4. relevant situation context

Base content priority:

1. mandatory Campaign information
2. primary problem/value
3. situation-relevant context
4. interest-matched supporting content
5. secondary Brand storytelling

Recommendations prioritize needs fit, then pain resolution, situation fit, and interest
fit. Behavior changes how choices are presented, not factual product relevance.

## 4. Behavior, journey, and combination decisions

- comparison-oriented → place comparable options/evidence close together
- self-directed research → preserve breadth, category paths, and detail access
- recommendation reliance → prioritize a curated recommendation with a reason
- high detail preference → move detail/proof earlier or use progressive disclosure
- quick decision → reduce optional introduction and candidate count
- awareness → explanatory/inspirational modules first; soft explore CTA
- exploration → broad discovery paths; browse/see-solutions CTA
- consideration → details, benefits, and comparison earlier; compare/view-details CTA
- decision → action-critical information earlier; direct supported Campaign CTA
- unknown journey → use the Campaign default CTA

Apply these combinations when both signals are supported:

- time constraint + comparison → curated shortlist followed by compact comparison
- information overload + detail preference → summary followed by progressive detail
- decision difficulty + recommendation reliance → recommendation plus reason
- decision difficulty + self-directed research → criteria followed by comparison
- low familiarity + detail preference → simple explanation before advanced detail
- decision stage + trust concern → proof, risk removal, then CTA
- cost concern + price comparison → supported price/conditions and comparison earlier

## 5. Realize using only supplied components

Each supplied body component may appear zero, one, or two times. Select components because
they support the persona strategy, omit irrelevant optional components, and repeat a
template only when its two occurrences serve distinct strategic roles. Every completed
page must contain at least five component occurrences in total. Personalize by
changing order, selecting an allowed layout, rewriting all editable copy, and choosing
persona-relevant imagery. Map strategies to the closest available component semantics:

- summary/value → hero, summary, or key-benefit component
- comparison → carousel, compare, card grid, or evidence component
- recommendation → curated cards or featured-content component
- exploration → category/navigation-like body content or broad carousel
- trust → proof, review, service, or evidence component
- action → CTA/banner component
- visual inspiration → hero, editorial, teaser, or image grid

Do not create a missing component or claim that an available component has unsupported
functionality. If no component matches, preserve the closest Campaign-default placement.

## 6. Validate each persona page

- The same Brand/Campaign facts remain identical across personas.
- Copy expresses a supported problem, value, or context instead of listing persona traits.
- Component order has a signal-based reason recorded in `component_strategy`.
- CTA intensity follows purchase journey only, not behavior or demographics.
- Component selection still preserves mandatory, legal, and offer-defining Campaign
  information in an appropriate selected component.
- `unsupported_inferences` records anything considered but rejected; normally it is empty.
- Pages for materially different personas should differ in copy emphasis, ordering,
  interaction strategy, or imagery whenever supported signals justify the difference.
