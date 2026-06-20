/**
 * Epsilon-Greedy AI - Based on GreedyAI
 * 
 * Same strategy as GreedyAI, but with random exploration
 */

class CustomAgent extends BalootAIAgent {
    constructor(playerIndex, teamIndex) {
        super(playerIndex, teamIndex);
        this.name = 'Epsilon-GreedyAI';
        this.version = '1.0.0';
        this.hand = [];
        this.playedCards = new Set();
        
        // === EPSILON-GREEDY PARAMETERS (only new addition) ===
        this.epsilon = 0.15;          // 15% random exploration
        this.epsilonDecay = 0.995;    // Decay rate
        this.minEpsilon = 0.05;       // Minimum exploration
    }

    // === NEW: Epsilon-greedy helpers ===
    shouldExplore() {
        return Math.random() < this.epsilon;
    }

    decayEpsilon() {
        this.epsilon = Math.max(this.minEpsilon, this.epsilon * this.epsilonDecay);
    }

    onRoundStart(roundInfo) {
        this.playedCards.clear();
        // this.decayEpsilon();  // Uncomment to decay each round
    }

    onReceiveHand(hand) {
        this.hand = [...hand];
    }

    // === MODIFIED: Added exploration to bidding ===
    async decideBid(biddingState) {
        // EXPLORATION: Random bid
        if (this.shouldExplore()) {
            return this.randomBid(biddingState);
        }
        
        // EXPLOITATION: Original greedy logic (unchanged)
        const { biddingCard, biddingRound } = biddingState;
        const hand = this.hand;
        const biddingCardSuit = biddingCard.suit;

        const suitCount = hand.filter(c => c.suit === biddingCardSuit).length;
        const hasJack = hand.some(c => c.suit === biddingCardSuit && c.rank === 'J');
        const hasNine = hand.some(c => c.suit === biddingCardSuit && c.rank === '9');

        if (biddingRound === 1) {
            if (suitCount >= 3 && (hasJack || hasNine)) {
                return { bidType: BID_TYPES.HOKUM };
            }

            const highCards = hand.filter(c => ['A', '10', 'K'].includes(c.rank)).length;
            if (highCards >= 5) {
                return { bidType: BID_TYPES.SUN };
            }

            return { bidType: BID_TYPES.PASS };

        } else {
            const suits = Object.values(SUITS).filter(s => s !== biddingCardSuit);
            let bestSuit = null;
            let bestScore = 0;

            for (const suit of suits) {
                const cards = hand.filter(c => c.suit === suit);
                let score = cards.length * 10;
                if (cards.some(c => c.rank === 'J')) score += 30;
                if (cards.some(c => c.rank === '9')) score += 20;
                if (cards.some(c => c.rank === 'A')) score += 10;

                if (score > bestScore) {
                    bestScore = score;
                    bestSuit = suit;
                }
            }

            if (bestScore >= 40 && bestSuit) {
                return { bidType: BID_TYPES.HOKUM_SECOND, suitChoice: bestSuit };
            }

            return { bidType: BID_TYPES.PASS };
        }
    }

    // === NEW: Random bid helper ===
    randomBid(biddingState) {
        const { validBids, biddingCard } = biddingState;
        const randomBid = validBids[Math.floor(Math.random() * validBids.length)];

        if (randomBid === BID_TYPES.HOKUM_SECOND) {
            const suits = Object.values(SUITS).filter(s => s !== biddingCard.suit);
            return { bidType: randomBid, suitChoice: suits[Math.floor(Math.random() * suits.length)] };
        }
        return { bidType: randomBid };
    }

    // === MODIFIED: Added exploration to card playing ===
    async decideCard(trickState, legalCards) {
        // EXPLORATION: Random card
        if (this.shouldExplore() && legalCards.length > 1) {
            return legalCards[Math.floor(Math.random() * legalCards.length)];
        }

        // EXPLOITATION: Original greedy logic (unchanged below)
        const { currentTrick, trumpSuit, gameType } = trickState;
        const partnerIndex = (this.playerIndex + 2) % 4;

        if (currentTrick.length === 0) {
            const nonTrump = legalCards.filter(c => c.suit !== trumpSuit);
            if (nonTrump.length > 0) {
                return this.getHighestCard(nonTrump, gameType, false);
            }
            return this.getHighestCard(legalCards, gameType, true);
        }

        const ledSuit = currentTrick[0].card.suit;
        const currentWinner = this.getCurrentWinner(currentTrick, trumpSuit, gameType);
        const partnerIsWinning = currentWinner && currentWinner.playerIndex === partnerIndex;

        if (partnerIsWinning) {
            return this.getLowestCard(legalCards, gameType, ledSuit === trumpSuit);
        }

        const winningCards = legalCards.filter(card =>
            this.cardBeats(card, currentWinner.card, ledSuit, trumpSuit, gameType)
        );

        if (winningCards.length > 0) {
            return this.getLowestCard(winningCards, gameType, legalCards[0]?.suit === trumpSuit);
        }

        return this.getLowestCard(legalCards, gameType, false);
    }

    // === ALL HELPERS UNCHANGED ===
    getHighestCard(cards, gameType, isTrump) {
        return cards.reduce((best, card) =>
            card.getRankingPower(gameType, isTrump) > best.getRankingPower(gameType, isTrump)
                ? card : best
        );
    }

    getLowestCard(cards, gameType, isTrump) {
        return cards.reduce((lowest, card) =>
            card.getRankingPower(gameType, isTrump) < lowest.getRankingPower(gameType, isTrump)
                ? card : lowest
        );
    }

    getCurrentWinner(trick, trumpSuit, gameType) {
        if (trick.length === 0) return null;
        const ledSuit = trick[0].card.suit;
        let winner = trick[0];

        for (let i = 1; i < trick.length; i++) {
            if (this.cardBeats(trick[i].card, winner.card, ledSuit, trumpSuit, gameType)) {
                winner = trick[i];
            }
        }
        return winner;
    }

    cardBeats(cardA, cardB, ledSuit, trumpSuit, gameType) {
        const aIsTrump = trumpSuit && cardA.suit === trumpSuit;
        const bIsTrump = trumpSuit && cardB.suit === trumpSuit;

        if (aIsTrump && !bIsTrump) return true;
        if (!aIsTrump && bIsTrump) return false;

        if (aIsTrump && bIsTrump) {
            return cardA.getRankingPower(gameType, true) > cardB.getRankingPower(gameType, true);
        }

        const aIsLed = cardA.suit === ledSuit;
        const bIsLed = cardB.suit === ledSuit;

        if (aIsLed && !bIsLed) return true;
        if (!aIsLed && bIsLed) return false;

        if (cardA.suit === cardB.suit) {
            return cardA.getRankingPower(gameType, false) > cardB.getRankingPower(gameType, false);
        }

        return false;
    }

    onCardPlayed(playerIndex, card) {
        this.playedCards.add(card.id);
    }
}