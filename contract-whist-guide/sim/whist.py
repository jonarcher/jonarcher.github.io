"""Three-player contract whist: cards, dealing, tricks, scoring, and a play policy.

Cards are the integers 0..51. suit = card // 13 (0 clubs, 1 diamonds, 2 hearts,
3 spades) and rank = card % 13 (0 is the 2, 12 is the ace), so within a suit a
bigger number is a higher card.

Seats are 0 (eldest hand: bids first, leads the first trick), 1, and 2 (the
dealer: bids last, and is barred from making the bids total the number of
tricks).
"""

RANKS = "23456789TJQKA"
SUITS = "CDHS"
JACK, QUEEN, KING, ACE = 9, 10, 11, 12


def suit(card):
    return card // 13


def rank(card):
    return card % 13


def name(card):
    return RANKS[card % 13] + SUITS[card // 13]


def deal(rng, n):
    """Deal n cards to each of three players and turn one card for trump.

    Returns (hands, turned). The turned card is out of play for the whole deal.
    """
    deck = list(range(52))
    rng.shuffle(deck)
    hands = [sorted(deck[i * n:(i + 1) * n]) for i in range(3)]
    return hands, deck[3 * n]


def score(bid, tricks):
    """One point a trick, plus ten for an exact bid."""
    return tricks + (10 if bid == tricks else 0)


def trick_winner(trick, led, trump):
    """trick is a list of (player, card). Returns the winning (player, card)."""
    best = None
    best_key = -1
    for player, card in trick:
        s = card // 13
        key = (2 if s == trump else 1 if s == led else 0) * 13 + card % 13
        if key > best_key:
            best, best_key = (player, card), key
    return best


def _top_unseen(seen_mask):
    """Rank of the highest card not in seen_mask (a 13-bit suit mask), or -1."""
    return (~seen_mask & 0x1FFF).bit_length() - 1


def choose(hand, trick, led, trump, bid, won, played, pos, greedy=False):
    """Pick a card to play.

    The policy steers toward the bid. While the player still needs tricks, or
    has already missed the bid so that every trick is worth a point, it tries
    to win. Once the bid is made it tries to lose, and sheds dangerous cards
    while doing so. greedy=True wins whenever it can, whatever the bid.

    hand: the player's cards. trick: (player, card) pairs played so far this
    trick. led: suit led, or -1 when leading. played: four suit masks of cards
    already played, including the turned trump card. pos: 0 when leading,
    1 second to play, 2 last.
    """
    if led >= 0:
        legal = [c for c in hand if c // 13 == led] or hand
    else:
        legal = hand
    if len(legal) == 1:
        return legal[0]

    want = greedy or bid != won
    seen = list(played)
    for c in hand:
        seen[c // 13] |= 1 << (c % 13)
    for _, c in trick:
        seen[c // 13] |= 1 << (c % 13)

    def key(c):
        s = c // 13
        return (2 if s == trump else 1 if s == led else 0) * 13 + c % 13

    def is_master(c):
        return c % 13 > _top_unseen(seen[c // 13])

    if led < 0:
        if want:
            trumps = [c for c in legal if c // 13 == trump]
            if trumps:
                top = max(trumps)
                if is_master(top):
                    return top
            best = None
            for c in legal:
                s = c // 13
                if s != trump and is_master(c):
                    k = (13 - seen[s].bit_count(), c % 13)
                    if best is None or k > best[0]:
                        best = (k, c)
            if best:
                return best[1]
            side = [c for c in legal if c // 13 != trump]
            return max(side or legal, key=rank)
        side = [c for c in legal if c // 13 != trump]
        return min(side or legal, key=rank)

    best_key = max(key(c) for _, c in trick)
    if want:
        beaters = [c for c in legal if key(c) > best_key]
        if beaters:
            if pos == 2:
                return min(beaters, key=key)
            masters = [c for c in beaters if is_master(c)]
            if masters:
                return min(masters, key=key)
            if beaters[0] // 13 == trump and led != trump:
                return min(beaters, key=key)
            return max(beaters, key=key)
        side = [c for c in legal if c // 13 != trump]
        return min(side or legal, key=rank)

    losers = [c for c in legal if key(c) < best_key]
    if losers:
        side = [c for c in losers if c // 13 != trump]
        if side:
            return max(side, key=rank)
        return max(losers, key=key)
    if pos == 2:
        return max(legal, key=key)
    return min(legal, key=key)


def play_hand(hands, trump, turned, bids, greedy=(False, False, False), record=None):
    """Play every trick. Returns the tricks each player won.

    If record is a list, (player, card) for each trick's winner is appended.
    """
    n = len(hands[0])
    hands = [list(h) for h in hands]
    played = [0, 0, 0, 0]
    played[turned // 13] |= 1 << (turned % 13)
    won = [0, 0, 0]
    leader = 0
    for _ in range(n):
        trick = []
        led = -1
        for pos in range(3):
            p = (leader + pos) % 3
            card = choose(hands[p], trick, led, trump, bids[p], won[p], played, pos, greedy[p])
            hands[p].remove(card)
            trick.append((p, card))
            if pos == 0:
                led = card // 13
        winner = trick_winner(trick, led, trump)
        won[winner[0]] += 1
        if record is not None:
            record.append(winner)
        for _, c in trick:
            played[c // 13] |= 1 << (c % 13)
        leader = winner[0]
    return won
