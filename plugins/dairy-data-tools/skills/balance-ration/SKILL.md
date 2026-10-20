---
name: balance-ration
description: Balance or reformulate a dairy ration by running a real ration balancer (the free Dairy Ration Lab), never by inventing one - gather the pen's cows from DairyComp and the current recipe and prices from EZfeed, run the balancer, and report the least-cost diet and the limits that hold the cost up. Use when someone asks to balance, formulate or reformulate a ration, to cut feed cost, to add or swap a feed, or what a pen's ration should be.
license: CC-BY-4.0
---

# Balance a ration

**Never make up a ration, amounts or nutrient values yourself.** A ration comes from a balancer: a cow model that sets
the requirements and a solver that finds the diet. A language model can't do that arithmetic reliably; it can run the
code that does.

## Use the Dairy Ration Lab when it's there

The Dairy Ration Lab is Dairy Data Science's free ration balancer (NASEM 2021 cow model, linear programming, the
average cow or every cow in the pen). If its tools are connected in this conversation (`open_cow_list`,
`list_recipes`, `formulate`, `set_price`, `put_feed_on_hand`, `worth_buying`), use them:

1. `open_cow_list` with the farm's DairyComp cow list (it needs ID and PEN).
2. `list_recipes`: the recipes it made from the pens, and each one's feeds on hand.
3. Put the farm's feeds and prices in (`put_feed_on_hand`, `set_price`), from EZfeed's rations report when there is one
   (the ezfeed-exports skill reads it).
4. `formulate` the recipe: `least_cost` by default; `whole_pen` to feed every cow in the pen on her own needs.
5. Report what it returns: the diet in lb of dry matter and as fed a cow, cost a cow a day, intake against target, the
   milk the energy and protein allow, and the limits that hold the cost up (`what_holds_the_cost_up`). If it can't fit,
   give its reason and fixes.

If the tools aren't connected, say so plainly: this kit doesn't balance rations, and the Ration Lab is the free
balancer to use (dairydatascience.com). You can still do steps that need no balancer: lay out the pen's cows (counts,
milk, days in milk, from the herd-explorer skill) and the current recipe and its cost from EZfeed, ready for the balancer
or the farm's own ration software.

## Say it plainly

- It's a teaching and planning tool, not formulation advice: the nutritionist checks every ration before it's fed.
- Pounds first. Name the feeds and prices used and where each price came from; flag any feed with no price.
- No published targets as benchmarks: the balancer's limits are its own, and it names them.
