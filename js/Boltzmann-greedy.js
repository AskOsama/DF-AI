/**
 * Probabilistic AI with Greedy Factor
 * 
 * Every decision is probability-weighted by how good each option is.
 * greedyFactor controls how much we favor the best option.
 */

class CustomAgent extends BalootAIAgent {
    constructor(playerIndex, teamIndex) {
        super(playerIndex, teamIndex);
        this.name = 'Probabilistic AI';
        this.version = '1.0.0';
        this.hand = [];
        this.playedCards = new Set();
        
        // GREEDY FACTOR (temperature inverse)
        // Higher = more greedy (picks best)
        // Lower = more random (explores)
        this.greedyFactor = 3.0;  // Try: 1.0 (random), 3.0 (balanced), 10.0 (very greedy)
    }

    onRoundStart(roundInfo) {
        this.playedCards.clear();
    }

    onReceiveHand(hand) {
        this.hand = [...hand];
    }

    // ============ SOFTMAX PROBABILITY SELECTION ============
    
    /**
     * Convert scores to probabilities and pick one
     * Higher greedyFactor = more likely to pick highest score
     */
    softmaxSelect(options, scores) {
        // Apply greedy factor (like inverse temperature)
        const expScores = scores.map(s => Math.exp(s * this.greedyFactor));
        const sum = expScores.reduce((a, b) => a + b, 0);
        const probabilities = expScores.map(s => s / sum);
        
        // Weighted random selection
        let r = Math.random();
        for (let i = 0; i < options.length; i++) {
            r -= probabilities[i];
            if (r <= 0) return options[i];
        }
        return options[options.length - 1];
    }

    // ============ PROBABILISTIC BIDDING ============

    async decideBid(biddingState) {
        const { biddingCard, biddingRound, validBids } = biddingState;
        const biddingCardSuit = biddingCard.suit;

        // Score each valid bid
        const bidOptions = [];
        const bidScores = [];

        for (const bid of validBids) {
            const score = this.scoreBid(bid, biddingCardSuit, biddingRound);
            bidOptions.push(bid);
            bidScores.push(score);
        }

        // Normalize scores to 0-1 range for better softmax behavior
        const maxScore = Math.max(...bidScores);
        const minScore = Math.min(...bidScores);
        const range = maxScore - minScore || 1;
        const normalizedScores = bidScores.map(s => (s - minScore) / range);

        // Select bid probabilistically
        const selectedBid = this.softmaxSelect(bidOptions, normalizedScores);

        // Handle suit choice for Hokum Second
        if (selectedBid === BID_TYPES.HOKUM_SECOND) {
            const bestSuit = this.findBestAlternativeSuit(biddingCardSuit);
            return { bidType: selectedBid, suitChoice: bestSuit };
        }

        return { bidType: selectedBid };
    }

    scoreBid(bid, biddingCardSuit, biddingRound) {
        const hand = this.hand;
        
        // Count trump strength
        const trumpCards = hand.filter(c => c.suit === biddingCardSuit);
        const trumpCount = trumpCards.length;
        const hasJack = trumpCards.some(c => c.rank === 'J');
        const hasNine = trumpCards.some(c => c.rank === '9');
        const hasAce = trumpCards.some(c => c.rank === 'A');
        
        // Count high cards for Sun
        const highCardCount = hand.filter(c => ['A', '10', 'K'].includes(c.rank)).length;

        if (bid === BID_TYPES.PASS) {
            // Pass is better when hand is weak
            let score = 0.5;  // Base score
            if (trumpCount < 2) score += 0.3;
            if (!hasJack && !hasNine) score += 0.2;
            if (highCardCount < 3) score += 0.1;
            return score;
        }

        if (bid === BID_TYPES.HOKUM) {
            // Hokum is better with strong trump
            let score = 0;
            score += trumpCount * 0.15;           // More trumps = better
            if (hasJack) score += 0.35;           // Jack is huge
            if (hasNine) score += 0.25;           // Nine is big
            if (hasAce) score += 0.1;
            if (trumpCount >= 4) score += 0.2;    // Bonus for 4+ trumps
            return score;
        }

        if (bid === BID_TYPES.SUN) {
            // Sun is better with many high cards
            let score = 0;
            score += highCardCount * 0.12;
            if (highCardCount >= 5) score += 0.3;
            if (highCardCount >= 6) score += 0.2;
            // Penalty if also have good trump (Hokum might be better)
            if (trumpCount >= 3 && (hasJack || hasNine)) score -= 0.2;
            return score;
        }

        if (bid === BID_TYPES.HOKUM_SECOND) {
            // Score based on best alternative suit
            const bestAltScore = this.scoreBestAlternativeSuit(biddingCardSuit);
            return bestAltScore;
        }

        return 0;
    }

    scoreBestAlternativeSuit(excludeSuit) {
        const suits = Object.values(SUITS).filter(s => s !== excludeSuit);
        let bestScore = 0;

        for (const suit of suits) {
            const cards = this.hand.filter(c => c.suit === suit);
            let score = cards.length * 0.1;
            if (cards.some(c => c.rank === 'J')) score += 0.35;
            if (cards.some(c => c.rank === '9')) score += 0.25;
            if (cards.some(c => c.rank === 'A')) score += 0.1;
            if (cards.length >= 4) score += 0.15;
            
            if (score > bestScore) bestScore = score;
        }
        return bestScore;
    }

    findBestAlternativeSuit(excludeSuit) {
        const suits = Object.values(SUITS).filter(s => s !== excludeSuit);
        let bestSuit = suits[0];
        let bestScore = 0;

        for (const suit of suits) {
            const cards = this.hand.filter(c => c.suit === suit);
            let score = cards.length * 10;
            if (cards.some(c => c.rank === 'J')) score += 30;
            if (cards.some(c => c.rank === '9')) score += 20;
            if (cards.some(c => c.rank === 'A')) score += 10;

            if (score > bestScore) {
                bestScore = score;
                bestSuit = suit;
            }
        }
        return bestSuit;
    }

    // ============ PROBABILISTIC CARD PLAYING ============

    async decideCard(trickState, legalCards) {
        if (legalCards.length === 1) {
            return legalCards[0];
        }

        const { currentTrick, trumpSuit, gameType } = trickState;
        
        // Score each legal card
        const cardScores = legalCards.map(card => 
            this.scoreCard(card, trickState, legalCards)
        );

        // Normalize scores
        const maxScore = Math.max(...cardScores);
        const minScore = Math.min(...cardScores);
        const range = maxScore - minScore || 1;
        const normalizedScores = cardScores.map(s => (s - minScore) / range);

        // Select card probabilistically
        return this.softmaxSelect(legalCards, normalizedScores);
    }

    scoreCard(card, trickState, legalCards) {
        const { currentTrick, trumpSuit, gameType } = trickState;
        const partnerIndex = (this.playerIndex + 2) % 4;
        const isLeading = currentTrick.length === 0;
        const isTrump = card.suit === trumpSuit;
        const cardPower = card.getRankingPower(gameType, isTrump);

        let score = 0;

        if (isLeading) {
            // === LEADING ===
            if (!isTrump) {
                // Prefer leading non-trump
                score += 0.2;
                // Prefer high cards to win the trick
                score += cardPower * 0.05;
            } else {
                // Leading trump - only good if we have many
                const trumpCount = legalCards.filter(c => c.suit === trumpSuit).length;
                if (trumpCount >= 4) {
                    score += 0.15;
                    score += cardPower * 0.04;
                } else {
                    score -= 0.1;  // Don't lead trump if few
                }
            }
        } else {
            // === FOLLOWING ===
            const ledSuit = currentTrick[0].card.suit;
            const currentWinner = this.getCurrentWinner(currentTrick, trumpSuit, gameType);
            const partnerIsWinning = currentWinner && currentWinner.playerIndex === partnerIndex;
            const canWin = this.cardBeats(card, currentWinner.card, ledSuit, trumpSuit, gameType);

            if (partnerIsWinning) {
                // Partner winning - play LOW (save good cards)
                score += (10 - cardPower) * 0.1;  // Lower card = higher score
            } else if (canWin) {
                // Can win - prefer LOWEST winning card
                score += 0.5;  // Bonus for winning
                score += (10 - cardPower) * 0.05;  // But prefer cheaper wins
            } else {
                // Can't win - dump LOWEST card
                score += (10 - cardPower) * 0.1;
            }

            // Penalty for wasting trump when not necessary
            if (isTrump && ledSuit !== trumpSuit && !canWin) {
                score -= 0.3;
            }
        }

        return score;
    }

    // ============ HELPERS (unchanged from GreedyAI) ============

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
```

## How It Works
```
EPSILON-GREEDY (before):          PROBABILISTIC (now):
┌─────────────────────────┐       ┌─────────────────────────┐
│ 85% → Best move         │       │ Score each option       │
│ 15% → Random (any move) │       │ Convert to probability  │
└─────────────────────────┘       │ Sample from distribution│
                                  └─────────────────────────┘

Example with 4 cards:

Epsilon-Greedy:                   Probabilistic (greedyFactor=3):
Card A (best):  85%               Card A (score 0.9): 60%
Card B (okay):  5%                Card B (score 0.7): 25%
Card C (bad):   5%                Card C (score 0.3): 10%
Card D (worst): 5%                Card D (score 0.1): 5%
         ↑                                 ↑
    Worst has same                   Worst has lowest
    chance as okay!                  chance (makes sense!)