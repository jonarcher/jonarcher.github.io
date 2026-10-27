# Contract whist: testing the bidding advice

This is the simulation behind Part 2 of [the guide](../). It plays three-player contract whist, with the rules from Part 1, and measures how well a bidding rule works.

It needs Python 3.10 or later and nothing else.

```sh
python3 tests.py                          # check the engine against hand-built deals
python3 experiments.py unit               # one-card win rates
python3 experiments.py values             # how often each kind of card wins a trick
python3 experiments.py guide --rule revised
python3 experiments.py oracle --rule revised
python3 experiments.py examples           # the example hands on the page
python3 check_page.py                     # recompute every figure quoted on the page
```

Add `--quick` for a small run. `--rule` picks `published` (the advice as first put up on 23 October 2026) or `revised` (the advice on the page now). Every run is seeded, so the same command prints the same figures. The full set takes about ten minutes on a ten-core laptop.

## What it models

- One deck, three players, hands of 1 to 7 cards, one card turned over for trump and then out of play. Seat 0 is the eldest hand, who bids first and leads. Seat 2 is the dealer, who bids last and can't make the bids total the number of tricks.
- A trick point for every trick won, and 10 more for an exact bid.
- The play policy is the same for every player (`choose` in `whist.py`). While a player still needs tricks, it leads its surest winner and wins as cheaply as it can. Once the bid is made, it leads low, plays the highest card that still loses, and sheds dangerous high cards. If the bid has been missed, every trick is worth a point, so it tries to win them all. It remembers which cards have gone.

The policy is a competent player, not an expert one. It beats random play by a wide margin (it hits its bid 46% of the time in 7-card deals, against 31% for random legal play), but it can't read opponents or bluff. Real tables will differ.

## The experiments

**unit** deals one card each and records how often each card wins. The results match the closed-form figures (printed beside them) within sampling error.

**values** has every player try to win every trick, and records how often each kind of card wins one. This is where the card values in the counting table start.

**guide** has all three players follow one bidding rule. It reports the score, the exact-bid rate and the average bid against the average tricks won, by hand size and seat. One check needs no play model at all: tricks always add up to the hand size, so a rule whose bids add up to much less than that must leave tricks over. The published rule's bids added up to about 4.3 in a 7-card deal. The revised rule's add up to about 6.5.

**oracle** takes a hand and tries every legal bid against 120 random deals of the other hands, then scores the best bid on 120 fresh deals, so the choice isn't flattered by luck. For the second and third bidders it keeps only deals in which the earlier players would have bid what they did. It reports how many points a rule gives up against the best bid ("regret").

**examples** does the same for the hands shown on the page.

## Results

Scores and exact-bid rates when all three players use the rule, averaged over the seats (300,000 deals per hand size):

| Cards | Published rule | Revised rule |
| --- | --- | --- |
| 1 | 6.81, 65% | 6.91, 66% |
| 2 | 6.03, 54% | 6.91, 63% |
| 3 | 5.75, 48% | 6.70, 57% |
| 4 | 5.78, 45% | 6.51, 52% |
| 5 | 5.94, 43% | 6.58, 49% |
| 6 | 6.04, 40% | 6.71, 47% |
| 7 | 6.25, 39% | 6.89, 46% |

The full tables, by seat, are in `results/`. The `oracle` runs also write one line per hand to `results/oracle-<rule>.jsonl`. Those files are large, so they aren't kept in the repository.

## How the revised rule was chosen

The published table counted the ace and king of trump in full, and gave most other trumps ½ only with three or more. Against the best bids it was low at every hand size, by about half a trick at 2–3 cards and about a trick at 6–7.

We fitted candidate counts to the best bids the `oracle` run found, and kept the simplest one that did nearly as well as the best of them. The values are in quarters of a trick, and nothing finer separated one choice from another. We then reran `guide` and `oracle` with all three players using the new rule, since the best bid for one player depends on how the others bid. The fitting scripts aren't included. The quarter-trick values in `revised_guide` (`players.py`) are all they produced.

Three refinements added little (0.06 points a hand at most) or nothing, so the rule leaves them out: extra credit for voids and short suits, different values by trump rank, and an adjustment for the earlier bids at the second seat. The dealer is the one place the earlier bids helped, and only in deals of four or more cards.
