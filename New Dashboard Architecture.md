# New Dashboard Architecture

## Architecture Summary

This document defines the proposed dashboard architecture in three layers. Layer 1 establishes the progressive-conversion principles and product psychology. Layer 2 turns those principles into the detailed acquisition, onboarding, premium-experience, pricing, analytics, and lifecycle model. Layer 3 is the latest refinement of the premium-experience timing and conversion sequence.

Core model:

Newsletter teaches the method → Dashboard lets the user perform the method → Premium improves the method → Bundle completes the method.

The central product rule is: never ask a new user to pay for intelligence they have not yet learned why they need. Every premium offer should appear immediately after the user encounters the problem that premium feature solves.

### Current recommended direction

Layer 3 is the latest refinement and supersedes Layer 2's 48-hour onboarding timing where the two differ. The current preferred model is a 7-Day Premium Welcome Experience that starts on the user's first dashboard visit, requires no card, introduces minimal selling during Days 1–2, introduces soft Complete Intelligence positioning around Day 3, uses the final 36 hours for conversion, and returns the user to a capable Free account after Day 7.

The Layer 2 pricing and five-question intelligence methodology remain foundational: Daily Intelligence Report at €8/month, GERI Live at €27/month, and EnergyRiskIQ Complete Intelligence at €29/month.

## Layer 1 — Progressive Conversion Principles

Yes — I would make progressive conversion a core UX rule for the EnergyRiskIQ dashboard, not merely a marketing adjustment.

The principle should be:

First create the “I understand how this helps me” moment. Then introduce the paid layer that makes that workflow better.

Right now, if a new user sees GERI Live, DIR, a 36-hour promotion, and several subscription CTAs almost simultaneously, each individual offer may be good — but collectively they can make the dashboard feel like a storefront before it feels like an intelligence product.

1. The ideal first-login psychology

A new user should mentally go through this sequence:

“What is happening?” → “Why does it matter?” → “What should I watch?” → “Can EnergyRiskIQ do more of this for me?”

Not:

“Welcome → Subscribe → Subscribe → Special offer → Upgrade.”

That distinction is important.

The first session should generate product comprehension and a small intelligence win.

For EnergyRiskIQ, that win should be the 3-Minute Energy Intelligence Routine.

I would effectively make that routine the onboarding mechanism.

2. First login: almost no selling

When the user first enters the dashboard, the strongest visual element should be something like:

Your 3-Minute Energy Intelligence Routine

1. Understand today's risk environment
GERI / EERI / market regime.

2. See whether risk is changing
Acceleration, intraday movement, emerging signals.

3. Understand what it means for markets
Oil, gas, LNG, scenarios and what to monitor next.

The CTA should not say Upgrade.

It should say:

Start My 3-Minute Briefing →

This psychologically transforms the dashboard from a collection of widgets into a workflow.

And importantly:

Do not display the large 36-hour subscription banner immediately above this experience.

That banner competes with the onboarding objective.

3. Step 1 should be completely educational

Imagine:

STEP 1 — What is the risk environment?

The user sees:

GERI

EERI

EGSI

risk regime

direction

recent change

And perhaps one concise interpretation:

Global energy risk remains elevated but is currently stabilising. European gas-market stress is moderately higher than yesterday.

Then:

Next: See whether risk is accelerating →

No subscription pitch yet.

This is important because the user hasn't experienced enough value to understand what they would be buying.

4. Step 2 becomes the natural GERI Live conversion point

Once the user reaches Step 2, the question changes:

Is risk changing right now?

This is precisely where GERI Live becomes relevant.

The user may see a limited/free version such as:

Current Risk Direction

↑ Increasing

Last daily GERI: 42

Intraday intelligence: restricted

Then underneath:

Markets don't wait for tomorrow's daily index.

GERI Live tracks how global energy risk is evolving intraday — helping you detect acceleration before it appears in the next daily reading.

See GERI Live →

Notice what happened here.

You're not saying:

Buy GERI Live.

You're saying:

You have reached a point in the intelligence workflow where intraday information would answer the question you're currently asking.

That is dramatically stronger conversion psychology.

5. Don't immediately open Stripe

This is another change I would make.

The first CTA shouldn't necessarily be:

Subscribe Now

It should be:

Explore GERI Live

Let them see the product.

Inside GERI Live you can then have:

Unlock Live Intelligence

That creates a micro-funnel:

Routine → curiosity → product preview → subscription

rather than:

Routine → payment request

You want the user to mentally purchase the capability before you ask them financially to purchase it.

6. Step 3 becomes the DIR conversion point

Now the user reaches:

STEP 3 — What does this mean for markets?

This is where the Daily Intelligence Report belongs naturally.

Give them enough free interpretation to demonstrate the concept.

For example:

Brent: Risk environment remains supportive, but confirmation from price action is required.

European Gas: Storage trajectory and geopolitical risk remain the primary variables to monitor.

LNG: Watch JKM/TTF divergence and supply-route developments.

Then present:

Want the full interpretation?

The Daily Intelligence Report turns EnergyRiskIQ's risk indicators, oil, gas and LNG data into:

• actionable takeaways
• market outlooks
• scenarios
• watchlists
• key events
• risk-management implications

Read Today's Intelligence Report →

Again, the positioning is not:

Here's another subscription.

It is:

You just asked, “What does all this mean?” Here is the product designed to answer exactly that.

7. This creates very clean product positioning

You now have an elegant relationship between the products:

Free EnergyRiskIQ Dashboard

What is happening?

↓

GERI Live

What is changing right now?

↓

Daily Intelligence Report

What does it mean and what should I watch next?

That is extremely important because it prevents GERI Live and DIR from looking like two unrelated subscriptions competing for attention.

They're actually different layers of the same intelligence workflow.

And this gives us the foundation for the bundle.

8. The bundle should appear only after the routine

After somebody completes Step 3, display something such as:

You've completed today's Energy Intelligence Routine

Then a small summary:

✓ Risk environment checked
✓ Risk direction checked
✓ Market implications reviewed

Now the commercial message:

Get the complete EnergyRiskIQ intelligence workflow

GERI Live

Know when risk is changing.

Daily Intelligence Report

Understand what that change means.

Unlock Complete Intelligence →

This is where the bundle feels completely logical.

The user understands why the two products belong together.

9. I would change the 36-hour offer substantially

The current concept of giving new users a limited-time opportunity is good.

I wouldn't remove it.

I would change when it appears.

Current likely experience

Register

↓

Dashboard

↓

36 HOURS LEFT! BUY SOMETHING

before the user knows much about EnergyRiskIQ.

That creates urgency without established value.

Better experience

Register

↓

Complete / partially complete 3-minute routine

↓

Discover GERI Live

↓

Discover DIR

↓

Then reveal the 36-hour introductory opportunity

Now urgency accelerates an existing desire rather than attempting to create desire.

That distinction matters.

10. The timer itself shouldn't begin visually at registration

There are two ways of handling this technically.

You can still internally define eligibility as 36 hours from signup.

But visually I would not make the countdown prominent until one of these events occurs:

Routine completed, GERI Live explored, DIR explored, or second dashboard session.

Then the banner can become:

New Member Intelligence Offer

Your introductory access offer expires in 29h 14m

Unlock the complete EnergyRiskIQ intelligence workflow.

View Offer →

That feels far less aggressive than presenting a countdown timer within seconds of signup.

11. The dashboard should remember where the user is

This becomes particularly powerful if you store onboarding state.

Something roughly like:

routine_started
step_1_viewed
step_2_viewed
geri_live_previewed
step_3_viewed
dir_previewed
routine_completed
bundle_offer_viewed

You don't need to make this complicated.

But it lets the dashboard adapt.

A completely new user sees mostly education.

A user who explored GERI Live sees more GERI Live-related messaging.

A user who read DIR sees more DIR messaging.

A user who completed everything can see the full bundle proposition.

A subscriber obviously stops seeing irrelevant upgrade messages.

This turns the dashboard into a behaviour-aware conversion funnel.

12. What happens on the second login?

The second login is actually where I would start becoming more commercial.

Instead of the original onboarding screen, greet them with:

Welcome back. Here's what changed since your last visit.

Then show the intelligence routine again.

But now the premium elements can be more visible.

For example:

GERI moved +4 since your previous session.

See what changed intraday → GERI Live

Or:

Oil risk increased while European gas stress declined.

See today's market implications → Daily Intelligence Report

Those CTAs are personalized to something happening in the product.

Much stronger.

13. Third login and onward

After several interactions, there's little reason to hide the paid products.

The dashboard can become the full EnergyRiskIQ intelligence workspace.

At that point the user understands:

Dashboard = orientation

GERI Live = monitoring

DIR = interpretation

You can therefore have GERI Live and DIR visibly represented permanently.

But now they are understood products rather than mysterious locked cards.

14. I would also reduce the number of identical "Subscribe" buttons

This is a subtle UX issue.

Five Subscribe / Upgrade / Unlock buttons do not necessarily produce five times the conversions.

Often they create banner blindness.

I would use different intent levels:

Low intent:

Learn More

Medium intent:

Explore GERI Live

Higher intent:

Unlock Live Intelligence

Purchase intent:

Start Subscription

The CTA should mature together with the user's journey.

15. I'd introduce one very useful concept: the Premium Preview

Rather than simply putting a 🔒 on paid information, give users a tiny glimpse.

For GERI Live:

Risk acceleration detected

GERI Live has changed materially since today's daily reading.

🔒 Intraday chart and driver analysis available with GERI Live.

For DIR:

3 market implications identified today

🔒 View today's Brent, TTF and LNG intelligence.

This is much better than:

PREMIUM CONTENT

Subscribe to see this.

It creates an information gap.

And information gaps are particularly powerful for intelligence products.

16. The entire onboarding funnel would therefore look like this

SIGNUP
   ↓
WELCOME TO ENERGYRISKIQ
   ↓
START 3-MINUTE INTELLIGENCE ROUTINE
   ↓
STEP 1
What's happening?
GERI / EERI / EGSI
NO SALE
   ↓
STEP 2
Is risk changing?
   ↓
GERI LIVE PREVIEW
"See what's happening intraday"
   ↓
STEP 3
What does this mean?
   ↓
DIR PREVIEW
"See today's interpretation"
   ↓
ROUTINE COMPLETE
   ↓
COMPLETE INTELLIGENCE OFFER
GERI LIVE + DIR
   ↓
36-HOUR INTRODUCTORY OFFER
   ↓
SUBSCRIPTION

That's the flow I would build.

17. There is another major benefit: it helps the newsletter strategy

This architecture fits the LinkedIn newsletter almost perfectly.

Your newsletter can repeatedly teach readers the same mental model:

What changed?

Why did it change?

Are markets confirming it?

What should you watch next?

Then when somebody creates an EnergyRiskIQ account, they encounter the same logic inside the product.

Newsletter → signup → dashboard → GERI Live → DIR therefore feels like one continuous intelligence experience, rather than separate marketing channels.

This is exactly what we want.

18. One change I would make to your current Dashboard

From the screenshots you showed in the previous discussion, I would not fundamentally redesign the dashboard.

The overall structure is already useful.

I would change the state of the dashboard depending on the user's maturity.

Essentially:

Same dashboard. Different emphasis.

For brand-new users, onboarding dominates.

For engaged free users, premium previews become visible.

For experienced free users, conversion becomes stronger.

For paying users, almost all sales messaging disappears and the dashboard becomes operational.

That is considerably better than maintaining separate dashboard designs.

19. I would define four user states

State	User behaviour	Dashboard objective
New	First session	Teach the intelligence routine
Exploring	Has interacted with features	Demonstrate premium capabilities
Engaged Free	Multiple sessions / routine completed	Convert to GERI Live / DIR / bundle
Subscriber	Has paid access	Deliver intelligence, minimize selling

This single concept can control most dashboard promotional behaviour.

20. And I would make one metric the primary onboarding KPI

Not:

How many people clicked Subscribe?

Initially measure:

What percentage of new accounts complete the 3-Minute Intelligence Routine?

Then track:

Routine started → Step 2 → GERI Live preview → Step 3 → DIR preview → routine completed → offer viewed → checkout → subscription

Now you have a real conversion funnel.

You will be able to identify whether the problem is:

product understanding,

GERI Live desirability,

DIR desirability,

pricing,

checkout,

or simply insufficient engagement.

Without this funnel, all you know is that someone registered and did/didn't subscribe.

The central rule I'd use

I would literally make this an internal EnergyRiskIQ product rule:

Never ask a new user to pay for intelligence they haven't yet learned why they need.

And then:

Every premium offer must appear immediately after the user encounters the problem that premium feature solves.

That's the essence of progressive conversion.

Applied properly, I think this can make the existing dashboard feel less commercial while actually becoming substantially better at converting users.

## Layer 2 — Core Acquisition and Conversion Architecture

Yes. I would turn this into the core acquisition and conversion architecture of EnergyRiskIQ rather than simply modifying a few banners.

The model becomes:

Newsletter teaches the method → Dashboard lets the user perform the method → Premium improves the method → Bundle completes the method.

And I would make one important change to your idea:

Do not start the 48-hour Premium Experience at registration. Start it when the user first reaches premium value — ideally Step 2.

Otherwise someone can register Tuesday evening, come back Thursday, and discover that most of the experience has disappeared.

1. The commercial architecture

I recommend this pricing:

Product	Price	Role
EnergyRiskIQ Free	€0	Orientation and daily risk monitoring
Daily Intelligence Report	€8/month	Interpretation
GERI Live	€27/month	Intraday risk monitoring + Brent Intelligence Forecast Engine™
Complete Intelligence Bundle	€29/month	GERI Live + DIR
Separate total	€35/month	—
Bundle saving	€6/month / ~17%	—

I strongly prefer €29 over €30, €31 or €32.

The psychology is especially powerful because:

GERI Live = €27
GERI Live + DIR = €29

So once somebody wants GERI Live, the decision becomes:

“For €2 more, I get the complete intelligence workflow.”

That should materially push people toward the bundle.

I would not introduce another introductory monthly discount initially.

The 48-hour unrestricted Premium Experience is already your acquisition incentive.

Too many incentives simultaneously — free trial + countdown + introductory discount + bundle discount + bonuses — weaken perceived product value.

2. What EnergyRiskIQ is actually selling

The products should no longer appear as isolated subscriptions.

The dashboard should teach this hierarchy:

EnergyRiskIQ Free

Where is risk now?

↓

GERI Live

Is that risk changing right now?

↓

Market confirmation

Are Brent, TTF, LNG and volatility confirming it?

↓

Daily Intelligence Report

What does it mean?

↓

Watchlist

What should I watch next?

That becomes the EnergyRiskIQ intelligence methodology.

And that's exactly what the newsletter should teach every week.

3. The new 5-step intelligence routine

I would expand the existing concept to five steps:

1. WHERE IS ENERGY RISK NOW?

2. IS RISK ACCELERATING OR FADING?

3. ARE MARKETS CONFIRMING THE SIGNAL?

4. WHAT DOES IT MEAN FOR ENERGY MARKETS?

5. WHAT SHOULD I WATCH NEXT?

This is much stronger than designing the dashboard around products.

The dashboard is organized around questions.

Products appear only when they answer those questions better.

4. First-login behavior

This is where I would make the biggest behavioral change.

Current behavior to avoid

A new user enters and sees:

GERI Live promotion
DIR promotion
36-hour promotion
subscription buttons
locked features
upgrade messages

before understanding the system.

New behavior

On first login the dominant component becomes:

Your 3-Minute Energy Intelligence Routine

Below it:

Five quick checks to understand today's energy-risk environment, whether conditions are changing, what markets are confirming and what you should watch next.

Primary CTA:

Start Today's 3-Minute Routine

There should be no major promotional banner above it.

No giant timer.

No “Subscribe Now.”

No bundle promotion yet.

You can still show GERI Live and DIR in navigation, but they should not dominate the page.

5. User lifecycle states

I would make the dashboard behavior state-driven.

State	Condition	Dashboard objective
NEW	Hasn't started routine	Teach
ACTIVATED	Routine started	Create first intelligence win
PREMIUM EXPERIENCE	48h experience activated	Demonstrate premium value
ENGAGED FREE	Experience expired	Convert
SUBSCRIBER	GERI/DIR/bundle customer	Deliver intelligence

The dashboard should behave differently for every state.

6. State 1 — New user

Top of dashboard:

Your 3-Minute Energy Intelligence Routine

Primary CTA:

Start Today's Routine

Then display the five steps visually.

For example:

✓ / ○  1. Risk Environment
○      2. Risk Direction
○      3. Market Confirmation
○      4. Market Implications
○      5. What to Watch

Do not show the bundle.

Do not show the countdown.

Do not aggressively sell DIR.

Do not aggressively sell GERI Live.

7. Step 1 — completely free

This must create the first value moment.

The user checks:

GERI
EERI
EGSI

and gets a concise interpretation.

No commercial message.

No upgrade banner.

Step 1 exists to teach:

“EnergyRiskIQ starts with risk, not price.”

That is also one of your strongest differentiators versus conventional market-data platforms.

8. Step 2 — introduce GERI Live

Now the user has seen the daily risk state.

The natural question becomes:

But is this changing?

That's where GERI Live appears.

This should be the first serious premium exposure.

Not before.

For users who haven't activated their Premium Experience:

Start your 48-hour Premium Experience

One click.

No payment card.

GERI Live unlocks.

DIR also unlocks.

Brent Intelligence Forecast Engine™ unlocks.

The 48-hour clock begins at this moment.

9. Why activating at Step 2 is strategically important

It means EnergyRiskIQ first demonstrates:

Problem

Daily GERI tells me the current risk state.

Then introduces:

Limitation

But daily data cannot tell me what's happening intraday.

Then introduces:

Solution

GERI Live.

This is exactly where the premium feature becomes valuable.

You aren't selling a feature.

You're solving the limitation the user has just discovered.

10. What happens when they activate the experience

Don't send them away to a pricing page.

Unlock GERI Live immediately.

Show a small confirmation:

Your 48-hour Premium Experience is active.

GERI Live, Daily Intelligence Report and the Brent Intelligence Forecast Engine™ are now unlocked.

No payment information required.

Then:

Open GERI Live →

The user should immediately experience the product.

11. Do NOT show a countdown immediately

This is important.

When the user starts the 48-hour experience, don't immediately show:

47:59:58 REMAINING!!!!!

That turns their exploration into a sales event.

For approximately the first 12 hours, just show a subtle status:

Premium Experience Active

That's enough.

12. Step 3 — Market Confirmation

This should largely remain free.

Question:

Are energy markets confirming the risk signal?

The user checks relevant market information:

Brent
TTF
JKM
VIX
possibly WTI
storage where relevant

The dashboard can synthesize them:

Market Confirmation: Partial

or:

Market Confirmation: Strong

or:

Market Confirmation: Diverging

This becomes a very valuable EnergyRiskIQ concept.

It prevents the user from assuming:

High risk = automatically bullish oil.

Instead:

Risk signal + market confirmation = stronger intelligence.

That's educationally valuable and improves credibility.

13. Step 4 — Introduce DIR

Now the natural question is:

Fine. What does all of this actually mean?

That's where DIR enters.

Not earlier.

During the 48-hour experience the full DIR should already be unlocked.

The CTA becomes:

Open Today's Intelligence Report

No “Subscribe.”

Let them read it.

You want them to experience:

Actionable Takeaways
Brent Outlook
TTF Outlook
LNG Outlook
Scenarios
Watchlist
Events
Risk Management Implications

before asking them to pay.

14. Step 5 — What should I watch next?

This becomes the conclusion of the routine.

It should synthesize the day's intelligence into a tiny watchlist.

For example:

TODAY'S WATCHLIST

→ GERI acceleration above [threshold]
→ Brent confirmation above/below [level]
→ TTF reaction to [factor]
→ Storage / LNG / geopolitical catalyst

The purpose is to answer:

What would make today's intelligence change?

That creates a reason to come back later.

Very important for retention.

15. After Step 5 — first bundle exposure

This is the point at which I would show the full bundle for the first time.

Not Step 1.

Not dashboard entry.

Not before the user understands DIR and GERI Live.

Immediately after completing the routine:

You've completed today's Energy Intelligence Routine.

Then:

✓ Risk environment checked
✓ Risk direction checked
✓ Market confirmation reviewed
✓ Market implications understood
✓ Watchlist established

And only then:

Keep the Complete Intelligence Workflow

GERI Live + Daily Intelligence Report

€29/month

That's the natural commercial conclusion.

16. Exact copy for the 5-step routine

Here is the copy I would use in the product.

Your 3-Minute Energy Intelligence Routine

Five quick checks to understand where energy risk stands, whether it is changing, whether markets are confirming the signal, what it means for key energy markets and what you should watch next.

Start Today's Routine →

STEP 1 OF 5
Where is energy risk now?

Start with the risk environment before looking at individual markets.

GERI shows the global energy-risk environment.
EERI shows European energy risk.
EGSI shows stress in Europe's natural-gas system.

Today's Risk Read

Global Energy Risk: [GERI VALUE] — [REGIME]

Direction: [RISING / STABLE / FALLING]

Europe Energy Risk: [EERI VALUE / STATUS]

European Gas Stress: [EGSI VALUE / STATUS]

What matters: Establish today's risk environment first. The next question is whether that risk is beginning to change.

Risk Checked — Continue →

STEP 2 OF 5
Is risk accelerating or fading?

Daily risk tells you where the market environment stands.

Intraday risk tells you whether that environment is changing right now.

Look for:

• accelerating risk
• fading risk
• sudden intraday jumps
• reversals
• changes in dominant risk drivers

Go Deeper With GERI Live

GERI Live tracks changes in global energy risk throughout the day, helping you identify acceleration or reversal before the next daily GERI reading.

Start My 48-Hour Premium Experience →

No payment information required.

During your Premium Experience, GERI Live, the Daily Intelligence Report and the Brent Intelligence Forecast Engine™ are fully unlocked.

When Premium Experience Is Active

GERI Live is unlocked.

See how global energy risk has changed since today's daily reading.

Open GERI Live →

After reviewing the live risk signal:

Risk Direction Checked — Continue →

STEP 3 OF 5
Are markets confirming the risk signal?

Risk by itself is not enough.

Now check whether energy markets are confirming, rejecting or diverging from the risk signal.

Review:

Brent — Is oil responding to the risk environment?

TTF — Is European gas stress appearing in price?

JKM LNG — Are global LNG markets confirming the move?

VIX / Market Risk — Is broader market volatility supporting the signal?

Market Confirmation

[STRONG / PARTIAL / WEAK / DIVERGING]

[Dynamic one- or two-sentence explanation.]

What matters: The strongest setups occur when risk direction and market behavior begin to confirm one another.

Market Confirmation Checked — Continue →

STEP 4 OF 5
What does this mean for energy markets?

Now turn the signals into market intelligence.

Today's Daily Intelligence Report connects EnergyRiskIQ's risk indicators with oil, European gas and LNG markets.

Inside today's report:

• Actionable Takeaways
• Brent Outlook
• TTF Outlook
• LNG Outlook
• Key Scenarios
• Market Watchlist
• Important Events
• Risk-Management Implications

During Your Premium Experience

Today's full Daily Intelligence Report is unlocked.

Open Today's Intelligence Report →

After The Premium Experience

Data tells you what changed.

The Daily Intelligence Report helps you understand what those changes may mean and what to watch next.

Preview Today's Intelligence →

Market Implications Reviewed — Continue →

STEP 5 OF 5
What should I watch next?

Finish your routine by identifying the signals that could confirm, weaken or reverse today's market setup.

Today's Intelligence Watchlist

Risk: [GERI / EERI / EGSI signal or threshold]

Oil: [Brent / WTI signal]

European Gas: [TTF / storage / EGSI signal]

LNG: [JKM / supply / shipping signal]

Key Catalyst: [event / geopolitical development / scheduled data]

The question to keep in mind

What would need to change for today's market view to change?

Knowing that answer makes it easier to recognize meaningful developments when they happen.

Complete Today's Routine →

Today's Energy Intelligence Routine Is Complete

✓ Risk environment checked
✓ Risk direction checked
✓ Market confirmation reviewed
✓ Market implications understood
✓ Watchlist established

Come back when conditions change — or run the routine again tomorrow.

Keep the Complete Intelligence Workflow
GERI Live + Daily Intelligence Report

GERI Live

Know when global energy risk is changing intraday.




Daily Intelligence Report

Understand what those changes may mean for Brent, TTF, LNG and the risks ahead.

Complete Intelligence

€29/month

GERI Live: €27/month
Daily Intelligence Report: €8/month

Save €6/month compared with subscribing separately.

The Brent Intelligence Forecast Engine™ is included with GERI Live.

Keep Complete Intelligence →

Continue using the free EnergyRiskIQ dashboard at any time.

This is the terminology I would standardize across the dashboard, newsletter and future marketing.

17. What happens during the first 12 hours of Premium Experience

Once they activate Step 2:

GERI Live

Fully unlocked.

DIR

Fully unlocked.

Brent Forecast Engine

Fully unlocked.

Premium indicators/features

Fully unlocked.

But there is no aggressive timer.

At the top of the relevant premium pages you can simply have:

48-Hour Premium Experience Active

And perhaps:

You're currently experiencing the complete EnergyRiskIQ intelligence workflow.

Nothing more.

18. Your existing 36-hour banner becomes useful here

This is where your current concept can actually become stronger.

The experience starts at 48 hours.

For the first 12 hours:

No countdown selling.

After 12 hours:

36 hours remain.

Now your existing 36-hour countdown concept appears naturally.

So you're not really deleting your existing mechanism.

You're repositioning it.

19. When exactly the 36-hour banner appears

Use this rule:

IF
Premium Experience is active

AND
12 hours have elapsed

AND
user has interacted with GERI Live OR DIR

THEN
show 36-hour Premium Experience banner

Even better:

If the user completes the entire routine before 12 hours, you can display the bundle card at Step 5, but still don't show an aggressive global countdown banner yet.

This keeps progressive conversion intact.

20. Exact 36-hour banner

At approximately 36 hours remaining:

Your Premium Experience Is Active

36 hours remaining

You currently have full access to:

GERI Live — monitor intraday changes in global energy risk

Daily Intelligence Report — understand the implications for Brent, TTF and LNG

Brent Intelligence Forecast Engine™ — explore risk-driven Brent scenarios

Continue using the complete EnergyRiskIQ intelligence workflow while your Premium Experience is active.

Continue Premium Experience →

Want to keep everything unlocked?

GERI Live + Daily Intelligence Report — €29/month

Save €6/month compared with separate subscriptions.

Keep Complete Intelligence →

Notice that even here the first CTA is:

Continue Premium Experience

not:

BUY NOW

The commercial CTA is secondary.

21. At 12 hours remaining, urgency becomes stronger

At this point the user has had approximately 36 hours to use the system.

Now urgency is legitimate.

The banner can become:

12 Hours Left in Your Premium Experience

Your access to GERI Live and the Daily Intelligence Report will return to the free level when your Premium Experience ends.

Keep the complete intelligence workflow available:

GERI Live + Daily Intelligence Report

€29/month

Instead of €35/month separately.

The Brent Intelligence Forecast Engine™ remains included with GERI Live.

Keep My Complete Intelligence Access →

Prefer to stay on EnergyRiskIQ Free? Your free dashboard will remain available.

That's the first point where I would make the conversion CTA dominant.

22. At 3 hours remaining

You can increase urgency one final time.

I would not use repeated popups.

Just change the existing banner:

3 hours left in your Premium Experience

Keep GERI Live + Daily Intelligence Report available without interruption.

Complete Intelligence — €29/month

Keep My Access →

No flashing red.

No giant countdown.

EnergyRiskIQ is a professional intelligence product, so the UX should remain restrained.

23. When the Premium Experience expires

Do not punish the user.

All free functions remain available.

Premium components gracefully move into preview mode.

Dashboard message:

Your Premium Experience has ended.

Your free EnergyRiskIQ dashboard remains available.

Restore GERI Live and Daily Intelligence Report whenever you want the complete intelligence workflow.

Restore Complete Intelligence — €29/month

This is much better than:

TRIAL EXPIRED. SUBSCRIBE NOW.

24. GERI Live banner behavior

There should actually be four different GERI Live states.

Before Step 2

No promotional banner.

At Step 2, before activation

Educational:

Daily risk tells you where conditions stand. GERI Live shows whether they're changing now.

CTA:

Start My 48-Hour Premium Experience

During experience

Status:

GERI Live is unlocked during your Premium Experience.

CTA:

Open GERI Live

After expiry

Conversion:

Continue monitoring global energy risk intraday.

GERI Live — €27/month

Or get GERI Live + DIR for €29/month.

At this point I would visually emphasize the bundle.

25. DIR banner behavior

Same logic.

Before Step 4

No DIR promotion.

At Step 4

Educational:

Data tells you what changed. Intelligence helps you understand what it means.

During Premium Experience:

Today's Daily Intelligence Report is unlocked.

CTA:

Open Today's Intelligence Report

After expiry:

Turn today's signals into actionable market intelligence.

Daily Intelligence Report — €8/month

Then beneath it:

Want live risk monitoring too?

Complete Intelligence — €29/month

26. The bundle should NOT be everywhere

This deserves a hard implementation rule.

Do not show the bundle:

On registration.

At the top of first login.

During Step 1.

Before the user has encountered either premium capability.

Soft bundle exposure can begin:

After Step 4.

Full bundle offer appears:

After Step 5 / routine completion.

Global bundle banner can appear:

After the first completed routine.

Or once the user has opened both:

GERI Live
and
DIR.

This makes the bundle feel earned.

27. What happens if someone only wants GERI Live

Don't force the bundle.

GERI Live remains:

€27/month

But the checkout or pricing card can say:

Add the Daily Intelligence Report for only €2 more/month.

This may become one of your highest-converting upsells.

Because the comparison becomes:

GERI Live                €27

Complete Intelligence    €29
GERI Live + DIR

The bundle should have the badge:

BEST VALUE

Not:

“Most Popular”

until you have actual evidence that it is.

28. What happens if someone wants DIR

DIR remains a very low-friction entry product:

€8/month

This is useful.

Some users may not care about intraday intelligence yet.

DIR can therefore function as your entry subscription.

Once they are paying €8 and develop a habit, you later expose:

Upgrade to Complete Intelligence

That's a healthy value ladder:

FREE
 ↓
DIR €8
 ↓
Complete €29

Another customer may follow:

FREE
 ↓
GERI LIVE €27
 ↓
Complete €29

Both routes work.

29. I would NOT call the bundle “GERI Live + DIR” everywhere

That's useful as a descriptor.

But I would give the commercial product a proper name.

My recommendation:

EnergyRiskIQ Complete Intelligence

Then below:

GERI Live + Daily Intelligence Report

So the pricing hierarchy becomes:

Daily Intelligence

€8/month

GERI Live

€27/month

Complete Intelligence

€29/month
GERI Live + Daily Intelligence Report

This is cleaner.

And it leaves room for more value to be added later.

30. Bonuses — don't introduce them immediately

I would use bonuses carefully.

The user should first want the product itself.

So:

Step 1

No bonus.

Step 2

Don't call anything a bonus.

Say:

Your Premium Experience also includes the Brent Intelligence Forecast Engine™.

That's an included capability, not a promotional gimmick.

Step 5

Now reinforce total value.

You can show:

COMPLETE INTELLIGENCE

GERI Live
+
Daily Intelligence Report
+
Brent Intelligence Forecast Engine™

Again, the forecast engine is part of GERI Live, so never pretend you're giving them something separately that was already included.

31. The first true “bonus” I'd create

I would make this newsletter-related.

Call it something like:

Newsletter Intelligence Companion

Every weekly LinkedIn newsletter edition gets a corresponding dashboard card.

Example:

This Week's Intelligence Companion

Newsletter topic:
Why Oil Risk Is Rising Even Before Brent Breaks Higher

Continue the analysis using today's live EnergyRiskIQ data.

Run This Week's Intelligence Routine →

That is an excellent connection between content and product.

Eventually Complete Intelligence subscribers could receive additional context such as:

What changed since publication
Latest GERI movement
Current Brent confirmation
Updated watchlist

That becomes a genuine premium newsletter companion.

32. This is how the newsletter should be structured

I would make every newsletter teach the same five questions.

Not necessarily literally using the same headings every week, but structurally:

1. Where does risk stand?

Current GERI/EERI/EGSI context.

2. Is risk changing?

Acceleration, deceleration, catalysts.

3. Are markets confirming it?

Brent / TTF / LNG / volatility.

4. What does it mean?

Interpretation.

5. What should we watch next?

Thresholds, events, scenarios.

Now readers gradually learn how EnergyRiskIQ thinks.

That's much more valuable than merely publishing market commentary.

33. The newsletter CTA

The main newsletter CTA should therefore usually not be:

Subscribe to GERI Live.

Instead:

Run Today's 3-Minute Energy Intelligence Routine

That takes them into the dashboard.

Then the dashboard itself performs progressive conversion.

This avoids making the LinkedIn newsletter look like an advert.

34. Newsletter → dashboard deep linking

I would implement links such as:

/dashboard/routine
?source=linkedin-newsletter
&edition=2026-09-02

Then when the user arrives, the dashboard can recognize the context.

Instead of generic:

Welcome to EnergyRiskIQ

show:

Continue This Week's Analysis

Run the live 3-Minute Energy Intelligence Routine using today's EnergyRiskIQ data.

That continuity can be very powerful.

35. The newsletter and dashboard now have distinct roles
LinkedIn Newsletter

Teach + provoke curiosity

↓

Free Dashboard

Validate the idea with real data

↓

GERI Live

Increase timeliness

↓

DIR

Increase interpretation

↓

Complete Intelligence

Combine monitoring + interpretation

This is a very clean acquisition funnel.

36. Returning-user dashboard behavior

Once someone has completed their first routine, stop treating them like a newcomer.

The hero changes from:

Start Your 3-Minute Intelligence Routine

to:

Today's 3-Minute Intelligence Routine

And possibly:

Last completed yesterday at 08:34.

Then show what changed:

3 meaningful changes since your last check

For example:

GERI ↑ 4
TTF ↓ 1.8%
EU storage +0.2pp

CTA:

Run Today's Routine →

Now you're building habit.

37. Second login is more important commercially than first login

On second login you can be slightly more assertive.

Example:

Welcome back — here's what changed since your last visit.

Then start the routine.

If Premium Experience is active:

Premium Experience Active — 31h remaining

That's acceptable now.

Because the user already understands EnergyRiskIQ.

38. Subscriber behavior should be completely different

Once someone subscribes:

Remove almost all sales messaging.

This is often overlooked.

A GERI Live subscriber shouldn't keep seeing:

Subscribe to GERI Live!

Likewise, a Complete subscriber should see essentially zero acquisition banners.

Their dashboard becomes an operational intelligence workspace.

For Complete users:

Today's Intelligence Routine

1 ✓ Risk Environment
2 ✓ GERI Live
3 ✓ Market Confirmation
4 ✓ Daily Intelligence
5 ✓ Watchlist

Everything is available.

That reinforces the value of their subscription every day.

39. One exception — GERI-only subscribers

Since the bundle costs only €2 more, a GERI Live-only customer may occasionally see:

Complete your intelligence workflow

Add the Daily Intelligence Report for just €2 more/month by switching to Complete Intelligence.

Don't show it every session.

Maybe once every 5–7 sessions or inside the Step 4 area.

40. DIR-only subscribers

When they reach Step 2:

Add intraday risk monitoring

Your Daily Intelligence subscription explains today's market environment. GERI Live adds intraday monitoring.

Upgrade to Complete Intelligence — €29/month

Again, context-specific.

41. Navigation behavior

Keep GERI Live and DIR visible in the sidebar.

Never completely hide premium features.

But adapt their labels.

For a free user:

GERI Live — Premium

Daily Intelligence — Premium

During Premium Experience:

GERI Live — Unlocked

Daily Intelligence — Unlocked

Complete subscriber:

GERI Live

Daily Intelligence

No lock badges.

42. What should happen with locked content after 48 hours

Don't completely hide it.

Use intelligent previews.

For GERI Live:

Risk acceleration detected

Intraday GERI has moved materially from today's daily reading.

🔒 See the full intraday movement and drivers.

For DIR:

4 market implications identified today

Brent: [small teaser]

🔒 View full oil, gas, LNG, scenario and watchlist analysis.

This creates curiosity through information gaps.

43. The top dashboard banner hierarchy

Never allow three competing banners.

I would enforce:

Maximum ONE primary dashboard banner at any time.

Priority:

1. Critical operational alert
2. First-login routine
3. Premium Experience status
4. Premium Experience expiry warning
5. Post-trial Complete Intelligence offer
6. Normal product promotion

If #2 is active, #5 cannot appear.

If #4 is active, don't simultaneously display separate GERI and DIR banners at the top.

Inline contextual cards can still exist.

44. 48-hour experience lifecycle

Here's the entire timing logic.

Registration

No clock starts.

Step 1

No premium offer.

Reaches Step 2

Offer:

Start My 48-Hour Premium Experience

User clicks

premium_experience_started_at = now

Everything unlocks.

Hour 0–12

No aggressive timer.

Status only:

Premium Experience Active

Hour 12–36

Show global banner:

36 hours remaining

Hour 36–45

Banner becomes:

12 hours remaining

Last 3 hours

Final reminder.

Hour 48

Return account to appropriate free/paid entitlement.

Display:

Your free EnergyRiskIQ dashboard remains available.

Then contextual bundle promotion.

45. What if they never activate the experience?

Don't start it.

Perhaps after the second or third visit you can gently show:

You still have a 48-hour Premium Experience available.

CTA:

Activate When You're Ready

This is much more user-friendly.

I would give the activation entitlement perhaps 7 days after registration.

So:

Start your 48-hour Premium Experience within your first 7 days.

That creates some urgency without wasting their trial.

46. I would make it no-card-required

For this particular product I strongly prefer:

48 hours free — no card required.

Your objective at this stage isn't collecting payment information.

It's showing users what GERI Live and DIR actually do.

Two days isn't long enough for massive abuse, and you can enforce:

one Premium Experience per account

plus normal abuse controls.

47. Don't give repeated free trials

Once used:

premium_experience_used = true

No second 48h period.

Occasional future reactivation campaigns are different, but don't make the onboarding experience repeatable.

48. Analytics events I would implement

You need to measure this funnel properly.

At minimum:

dashboard_first_view

routine_impression
routine_started

routine_step_1_viewed
routine_step_1_completed

routine_step_2_viewed
premium_experience_offer_viewed
premium_experience_started
geri_live_opened

routine_step_2_completed

routine_step_3_viewed
routine_step_3_completed

routine_step_4_viewed
dir_opened
routine_step_4_completed

routine_step_5_viewed
routine_completed

bundle_offer_viewed
bundle_cta_clicked

checkout_started
subscription_started

premium_experience_36h_banner_viewed
premium_experience_12h_banner_viewed
premium_experience_expired

newsletter_dashboard_visit
newsletter_routine_started
newsletter_conversion

These are strategically much more valuable than tracking generic pageviews.

49. Your primary activation metric

I would make this:

% of registered users who complete their first 3-Minute Intelligence Routine

That's your activation KPI.

Then:

Activation funnel

Signup

→ routine started

→ Step 2 reached

→ Premium Experience activated

→ GERI Live used

→ DIR used

→ routine completed

→ Complete offer viewed

→ paid

Now you will know where conversion fails.

50. Important secondary metrics

I'd watch:

Routine start rate

Routine completion rate

48h Premium activation rate

% of trial users who open GERI Live

% who open DIR

% who use both

Trial → any paid

Trial → Complete Intelligence

GERI Live standalone → bundle

DIR → bundle

Newsletter → signup

Newsletter signup → routine completion

Newsletter → paid

And especially:

Users who experience both GERI Live and DIR versus conversion rate

My expectation is that this group should convert materially better.

51. Dashboard visual hierarchy

The top should roughly become:

ENERGYRISKIQ DASHBOARD

Good morning / Current Date

YOUR 3-MINUTE ENERGY INTELLIGENCE ROUTINE
[progress bar]

Step 1
Step 2
Step 3
Step 4
Step 5

------------------------------------

Market / index dashboard modules

------------------------------------

Premium contextual modules

------------------------------------

Newsletter Intelligence Companion

This makes the routine an orchestration layer over the dashboard rather than a separate product.

52. A progress bar will help

Example:

Today's Routine — 3 of 5 complete

██████████░░░░

Then:

Continue: What does this mean for markets?

This makes returning to the dashboard obvious.

And it introduces some light completion psychology without gamifying a professional intelligence product too heavily.

53. Persist daily completion state

The routine should reset each new intelligence day.

For example:

routine_date
step_1_complete
step_2_complete
step_3_complete
step_4_complete
step_5_complete

Next day:

new routine.

But retain history such as:

Last completed: Yesterday

Eventually you might even show:

6 routines completed this week

but I would consider that Phase 2.

54. Don't force users through the steps linearly

The recommended order is 1 → 5.

But sophisticated users should be able to click any step.

A trader may go directly to GERI Live.

An analyst may go directly to DIR.

So the routine guides.

It doesn't imprison.

55. The backend state model can remain simple

Something roughly like:

onboarding_state:
  new
  routine_started
  routine_completed

premium_experience:
  eligible
  active
  expired
  converted

premium_experience_started_at
premium_experience_expires_at

geri_live_seen
dir_seen

bundle_offer_seen

subscription:
  free
  dir
  geri_live
  complete

You do not need a huge personalization engine to implement this.

56. The critical conditional logic

Conceptually:

IF complete_subscriber
    hide all acquisition banners

ELSE IF first_login AND routine_not_started
    show routine onboarding
    hide sales banner

ELSE IF premium_experience_active AND remaining > 36h
    show subtle Premium Experience status

ELSE IF premium_experience_active AND remaining <= 36h
    show Premium Experience countdown banner

ELSE IF premium_experience_expired AND routine_completed
    show Complete Intelligence offer

ELSE
    show contextual product promotions only

Then Step 2 controls GERI Live promotion.

Step 4 controls DIR promotion.

Step 5 controls bundle promotion.

That one architecture solves most of the current sales-exposure issue.

57. How this changes your existing banner strategy

You currently have several possible selling surfaces.

I would turn them into this:

Dashboard global banner

Used for state, not random product promotion.

Step 2 inline card

GERI Live.

Step 4 inline card

DIR.

Step 5 completion card

Complete Intelligence.

GERI Live page

GERI-specific conversion.

DIR page

DIR-specific conversion.

Pricing page

Full product comparison.

Each surface gets one job.

58. Pricing page should reinforce the intelligence model

I wouldn't present three generic SaaS pricing cards.

Use:

Daily Intelligence

Understand what it means

€8/month

GERI Live

Know when risk is changing

€27/month

Complete Intelligence

Know what's changing — and what it means

€29/month

BEST VALUE

GERI Live
Daily Intelligence Report
Brent Intelligence Forecast Engine™

Save €6/month.

This reinforces the methodology.

59. Don't advertise “all premium features” indefinitely

For the trial, yes:

48-Hour Premium Experience

But eventually enumerate what's included.

“All Premium Features” can sound generic.

Better:

Experience the complete EnergyRiskIQ intelligence workflow for 48 hours.

Then name:

GERI Live
DIR
Brent Forecast Engine

That communicates actual value.

60. The terminology I would standardize

I would use these exact concepts everywhere:

Routine

3-Minute Energy Intelligence Routine

Trial

48-Hour Premium Experience

Not “free trial” as the main wording.

Bundle

Complete Intelligence

GERI Live benefit

Know when risk is changing.

DIR benefit

Understand what it means.

Combined benefit

Know what's changing — and what it means.

That becomes your messaging architecture.

61. The single sentence that connects everything

I would use some variation of this throughout EnergyRiskIQ:

Start with risk. Check whether it's changing. See whether markets confirm it. Understand what it means. Know what to watch next.

That is essentially the EnergyRiskIQ methodology in one sentence.

And that methodology can underpin:

the dashboard
the newsletter
email marketing
LinkedIn posts
Medium articles
product onboarding
GERI Live
DIR
eventually your pricing page

62. Implementation order

I wouldn't build everything simultaneously.

Phase 1 — Conversion architecture

Implement:

5-step routine
progress state
contextual GERI Live exposure
contextual DIR exposure
Complete Intelligence €29 bundle
banner suppression rules

Phase 2 — Premium Experience

Implement:

48-hour activation
trial entitlement
12/36/48-hour states
expiry behavior
no-card activation

Phase 3 — Analytics

Implement all funnel events.

Do this before aggressively driving newsletter traffic.

Phase 4 — Newsletter integration

Create:

newsletter deep links
edition/source tracking
“Continue this week's analysis” card
common five-question framework

Phase 5 — Behavioral personalization

Add:

welcome-back changes
last-session comparisons
re-engagement
subscriber-specific dashboard states
newsletter companion intelligence

63. What I would NOT do

I would specifically avoid:

A large 48-hour countdown immediately after signup.

GERI Live and DIR subscription banners simultaneously on first login.

A bundle offer before the user understands both products.

A credit-card-required 48-hour experience.

Discounting €29 further during onboarding.

Repeated popups.

Hiding premium products completely.

Making users complete all five steps before they can use the dashboard.

Calling everything AI/premium/pro.

The product should feel like professional market intelligence, not an aggressive SaaS funnel.

64. The complete user journey

Ultimately, this is what I would build:

LINKEDIN NEWSLETTER
        ↓
Learn EnergyRiskIQ's 5-question methodology
        ↓
CTA
"Run Today's 3-Minute Intelligence Routine"
        ↓
ACCOUNT / DASHBOARD
        ↓
STEP 1
Where is energy risk now?
FREE VALUE
        ↓
STEP 2
Is risk accelerating?
        ↓
Discover limitation of daily data
        ↓
START 48-HOUR PREMIUM EXPERIENCE
        ↓
GERI LIVE
        ↓
STEP 3
Are markets confirming?
        ↓
Brent / TTF / LNG / VIX
        ↓
STEP 4
What does it mean?
        ↓
DAILY INTELLIGENCE REPORT
        ↓
STEP 5
What should I watch next?
        ↓
ROUTINE COMPLETE
        ↓
COMPLETE INTELLIGENCE
GERI LIVE + DIR
€29/MONTH
        ↓
FIRST 12 HOURS
Explore — minimal selling
        ↓
36 HOURS REMAINING
Soft conversion banner
        ↓
12 HOURS REMAINING
Strong conversion banner
        ↓
EXPIRES
Free dashboard remains
        ↓
Contextual upgrade opportunities
The strategic outcome

This changes EnergyRiskIQ from:

a dashboard containing several free and paid tools

into:

an intelligence methodology that users learn, repeat and eventually pay to perform at a deeper level.

That distinction is enormous.

And the newsletter then stops being merely a traffic generator. It becomes the education layer of the product funnel.

The newsletter teaches the five questions.

The dashboard answers them with live data.

GERI Live improves timeliness.

DIR improves interpretation.

And Complete Intelligence at €29/month becomes the natural product for someone who wants the entire workflow.

## Layer 3 — Revised 7-Day Premium Welcome Experience

Yes — with one important modification: I would increase the Premium Experience substantially, but I would not then offer a second conventional free trial immediately afterward.

For EnergyRiskIQ, I think 48 hours is too short to demonstrate the real value of GERI Live + DIR. These are intelligence products whose value becomes clearer through repeated use and changing market conditions.

My preferred model now would be:

Registration → 7-Day Premium Welcome Experience → Free account or paid subscription

And I would actually prefer this over the 48-hour model we designed above.

Why 7 days fits EnergyRiskIQ better

A new user needs time to see different market conditions. In 48 hours, GERI Live might barely move, there may be no meaningful geopolitical development, and the DIR may look similar on consecutive days. The user could conclude that the premium products aren't particularly valuable simply because they experienced them during a quiet two-day window.

Seven days gives them up to:

7 Daily Intelligence Reports
multiple GERI Live sessions
opportunities to see risk accelerate/fade
several Brent/TTF/LNG movements
repeated use of the Brent Intelligence Forecast Engine™
an entire weekly Newsletter → Dashboard intelligence cycle
enough repetition for the 3-Minute Intelligence Routine to begin becoming a habit

That last point is especially valuable.

I would change the model to this
Day 0 — Registration

Account created.

The first dashboard message is not:

Start your free trial.

Instead:

Welcome to EnergyRiskIQ

Your 7-Day Premium Welcome Experience is active.

For the next 7 days, you can experience the complete EnergyRiskIQ intelligence workflow — including GERI Live, the Daily Intelligence Report and the Brent Intelligence Forecast Engine™.

Start Today's 3-Minute Intelligence Routine →

No card.

No checkout.

No pricing wall.

No aggressive timer.

The user is simply inside the product.

That is important.

A subtle technical change

I wouldn't actually start the seven-day clock at the instant they submit the registration form.

Start it when they enter the dashboard for the first time.

For example:

registered_at
first_dashboard_visit_at
premium_experience_started_at
premium_experience_expires_at

So someone who registers Tuesday night but doesn't come back until Thursday hasn't wasted two days.

From the user's perspective it still feels like:

Premium access included when I joined.

But technically the experience starts when they can actually use it.

Days 0–2: absolutely minimal selling

This is where I would modify our previous progressive-conversion plan.

Because GERI Live and DIR are already unlocked, there is no reason to sell them during Steps 2 and 4.

Instead, teach the user why they matter.

For example:

Step 2

Is risk accelerating or fading?

Your Premium Welcome Experience includes GERI Live.

See how global energy risk has evolved since today's daily reading.

Open GERI Live →

Not:

Subscribe to GERI Live.

And Step 4:

What does this mean for energy markets?

Today's Daily Intelligence Report is included in your Premium Welcome Experience.

Read Today's Intelligence →

So the user experiences premium as part of EnergyRiskIQ rather than constantly being reminded that they're temporarily using paid features.

This is actually psychologically stronger.

Day 3 is when I would first introduce pricing

By now the user has hopefully completed several routines.

A very subtle dashboard card can appear after routine completion:

You're experiencing EnergyRiskIQ Complete Intelligence

Your Premium Welcome Experience includes:

GERI Live
Daily Intelligence Report
Brent Intelligence Forecast Engine™

After your Premium Experience, keep Complete Intelligence for €29/month.

CTA:

Learn About Complete Intelligence

Still no urgency.

No countdown.

Days 4–5: establish ownership

This is an important psychological stage.

Instead of saying:

Here's what you could buy.

EnergyRiskIQ should reinforce:

Here's what you've been using.

For example after completing the routine:

Today's Complete Intelligence Routine

✓ Risk environment
✓ Intraday risk
✓ Market confirmation
✓ Market interpretation
✓ Watchlist

Then underneath:

Your Premium Welcome Experience keeps this complete workflow unlocked until [date].

Now you're beginning to establish loss aversion naturally.

The user understands what will disappear because they've actually used it.

Day 6 — your 36-hour banner becomes excellent

This is where I think your existing 36-hour countdown idea should survive.

But instead of starting at registration, it becomes the final conversion phase of the seven-day experience.

Approximately 36 hours before expiry:

Your Premium Welcome Experience Ends in 36 Hours

You've been using the complete EnergyRiskIQ intelligence workflow.

Keep:

GERI Live — €27/month
Daily Intelligence Report — €8/month

Or keep both with:

EnergyRiskIQ Complete Intelligence

€29/month

Save €6/month compared with subscribing separately.

Keep Complete Intelligence →

This makes vastly more sense than showing the same banner shortly after registration.

At this point the user actually knows what they would lose.

Final 12 hours

Now I would become much more conversion-focused.

12 Hours Left

Your Premium Welcome Experience ends today.

After it ends, your free EnergyRiskIQ dashboard remains available. GERI Live and the full Daily Intelligence Report will return to Premium access.

Keep Complete Intelligence — €29/month

GERI Live + Daily Intelligence Report + Brent Intelligence Forecast Engine™

Keep My Complete Intelligence Access →

And I'd explicitly reassure:

Your EnergyRiskIQ Free account will continue normally if you don't subscribe.

That reduces pressure.

After seven days

No surprise credit-card charge because we never collected one.

The account gracefully becomes Free.

GERI Live becomes premium preview.

DIR becomes premium preview.

Free dashboard functionality continues.

The message becomes:

Your Premium Welcome Experience Has Ended

Your EnergyRiskIQ Free account remains active.

You can continue monitoring today's energy-risk environment using the free dashboard.

Want the complete workflow again?

Complete Intelligence — €29/month

GERI Live + Daily Intelligence Report

Restore Complete Intelligence →

This is a much cleaner relationship with the user.

Would I then offer another free trial?

No — not as the normal onboarding flow.

I would avoid:

7 days Premium Experience
↓
Then 14-day free trial
↓
Then maybe pay

because psychologically you're teaching the customer:

“There will always be another free period.”

And your monetization event gets pushed further and further away.

Worse, someone could receive three weeks of premium intelligence before deciding whether €29/month is worth paying.

That's unnecessary.

Instead:

The 7-Day Premium Welcome Experience IS the free trial — but don't call it a trial.

That's the distinction I would make.

Why “Premium Welcome Experience” is better than “Free Trial”

“Free Trial” focuses on the transaction:

Try before paying.

“Premium Welcome Experience” focuses on onboarding:

We're letting you experience EnergyRiskIQ properly.

It also fits progressive conversion better.

For your audience — traders, analysts, risk professionals — I prefer the latter.

It feels less like conventional SaaS marketing.

There is one place where I'd use another free-access opportunity later

Not immediately.

For users who didn't convert but remain engaged for, say, 30–60 days, you could occasionally offer:

24-Hour Complete Intelligence Pass

Triggered by a particularly significant market event.

Example:

Global energy risk has risen sharply today.

We've temporarily reopened your Complete Intelligence access for the next 24 hours so you can follow the event using GERI Live and today's Daily Intelligence Report.

That could be extremely effective.

It's not another generic trial.

It's event-driven reactivation.

And because EnergyRiskIQ is an intelligence product, this approach fits the product exceptionally well.

I also think seven days aligns much better with the Newsletter

This might be the strongest argument for changing from 48 hours.

Imagine somebody comes from Wednesday's LinkedIn Newsletter.

Wednesday

Reads newsletter.

↓

Creates EnergyRiskIQ account.

↓

7-Day Premium Welcome Experience begins.

↓

Runs first 3-Minute Routine.

Thursday

Returns and sees how signals changed.

Friday

Runs another routine.

Reads DIR.

Weekend

Checks developments.

Monday

Compares conditions.

Tuesday

Next market setup begins developing.

Wednesday

Receives/sees the next Newsletter edition while still finishing their Premium Experience.

That's very powerful.

They have now experienced:

Newsletter → live dashboard → GERI Live → DIR → another newsletter cycle.

The entire EnergyRiskIQ ecosystem has been demonstrated.

A 48-hour trial cannot do that.

Therefore I would revise our funnel

Instead of:

Newsletter
↓
Signup
↓
Free Dashboard
↓
Step 2
↓
Activate 48h Premium
↓
36h countdown
↓
Pay

I would now use:

LINKEDIN NEWSLETTER
        ↓
SIGNUP
        ↓
FIRST DASHBOARD VISIT
        ↓
7-DAY PREMIUM WELCOME EXPERIENCE STARTS
        ↓
3-MINUTE INTELLIGENCE ROUTINE
        ↓
DAY 1–2
LEARN + EXPERIENCE
Almost no selling
        ↓
DAY 3
Introduce Complete Intelligence
€29/month
        ↓
DAY 4–5
Reinforce habitual use
        ↓
FINAL 36 HOURS
Conversion banner begins
        ↓
FINAL 12 HOURS
Strong conversion CTA
        ↓
DAY 7
Premium Experience ends
        ↓
FREE ACCOUNT REMAINS
        ↓
GERI Live/DIR previews
        ↓
€8 DIR / €27 GERI / €29 Complete
And I'd make one more change to our previous plan

With a seven-day Premium Welcome Experience, the bundle should probably not be prominently presented immediately after the user's very first completed routine.

Previously I recommended that.

I would now delay the strong €29 bundle presentation until approximately Day 3 or after the user's second/third routine, whichever comes first.

The first completed routine should finish with:

Great — you've completed today's Energy Intelligence Routine. Come back tomorrow to see what changed.

That is more valuable at this stage than:

Now buy €29/month.

The first goal becomes repeat usage.

The sale comes after repeated value.

So my preference is now:

7-Day Premium Welcome Experience — no card required

Days 1–2: education and product experience
Days 3–5: soft Complete Intelligence positioning
Final 36h: conversion campaign
After Day 7: Free account + contextual premium previews

And keep:

DIR — €8/month
GERI Live — €27/month
EnergyRiskIQ Complete Intelligence — €29/month

I think this is materially stronger than the 48-hour model, especially because GERI Live and DIR need several market sessions to demonstrate why somebody would want them every day.
