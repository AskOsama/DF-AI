/**
 * StrategicAI - Team 2 Default Agent
 *
 * Strategy: Card-tracking probabilistic AI
 * - Tracks all played cards to know what remains
 * - Evaluates hand strength with weighted scoring
 * - Makes probabilistic decisions based on remaining cards
 * - Fights harder for high-value tricks
 * - Leads with trump in late game to extract remaining trumps
 *
 * This file can be loaded via the AI Upload feature to test the loading mechanism.
 *
 * @author DS-AI Course
 * @version 1.0.0
 */

class CustomAgent extends BalootAIAgent {
    constructor(playerIndex, teamIndex) {
        super(playerIndex, teamIndex);
        this.name = 'StrategicAI';
        this.version = '1.0.0';
        this.hand = [];
        this.playedCards = [];
        this.suitCounts = { clubs: 8, diamonds: 8, hearts: 8, spades: 8 };
    }

    /**
     * Reset tracking at round start
     */
    onRoundStart(roundInfo) {
        this.playedCards = [];
        this.suitCounts = { clubs: 8, diamonds: 8, hearts: 8, spades: 8 };
    }

    /**
     * Update suit counts when receiving hand
     */
    onReceiveHand(hand) {
        this.hand = [...hand];
        // Subtract our cards from suit counts (cards we can see)
        for (const card of hand) {
            this.suitCounts[card.suit]--;
        }
    }

    /**
     * Decide what to bid
     * Strategy: Weighted evaluation of hand strength
     */
    async decideBid(biddingState) {
        const { biddingCard, biddingRound } = biddingState;
        const hand = this.hand;

        const handScore = this.evaluateHand(hand, biddingCard.suit);

        if (biddingRound === 1) {
            // Hokum threshold: 65 points
            if (handScore.hokumScore > 65) {
                return { bidType: BID_TYPES.HOKUM };
            }
            // Sun threshold: 75 points (need stronger hand for Sun)
            if (handScore.sunScore > 75) {
                return { bidType: BID_TYPES.SUN };
            }
            return { bidType: BID_TYPES.PASS };

        } else {
            // Second round: evaluate all alternative suits
            let bestSuit = null;
            let bestScore = 0;

            for (const suit of Object.values(SUITS)) {
                if (suit !== biddingCard.suit) {
                    const score = this.evaluateSuitAsHokum(hand, suit);
                    if (score > bestScore) {
                        bestScore = score;
                        bestSuit = suit;
                    }
                }
            }

            // Lower threshold for second round (55)
            if (bestScore > 55 && bestSuit) {
                return { bidType: BID_TYPES.HOKUM_SECOND, suitChoice: bestSuit };
            }

            // Also consider Sun with lower threshold
            if (handScore.sunScore > 55) {
                return { bidType: BID_TYPES.SUN };
            }

            return { bidType: BID_TYPES.PASS };
        }
    }

    /**
     * Evaluate hand strength for bidding
     * Returns both Hokum and Sun scores
     */
    evaluateHand(hand, potentialTrump) {
        let hokumScore = 0;
        let sunScore = 0;

        // Hokum evaluation - trump suit strength
        const trumpCards = hand.filter(c => c.suit === potentialTrump);
        hokumScore += trumpCards.length * 12;  // Base: 12 per trump card
        if (trumpCards.some(c => c.rank === 'J')) hokumScore += 25;  // Jack is very valuable
        if (trumpCards.some(c => c.rank === '9')) hokumScore += 18;  // Nine is second strongest
        if (trumpCards.some(c => c.rank === 'A')) hokumScore += 8;   // Ace is useful

        // Sun evaluation - high cards across all suits
        const aces = hand.filter(c => c.rank === 'A').length;
        const tens = hand.filter(c => c.rank === '10').length;
        const kings = hand.filter(c => c.rank === 'K').length;

        sunScore += aces * 15;   // Aces are very strong in Sun
        sunScore += tens * 8;    // Tens are valuable
        sunScore += kings * 4;   // Kings help

        // Suit distribution bonus for Sun
        const suits = {};
        for (const card of hand) {
            suits[card.suit] = (suits[card.suit] || 0) + 1;
        }
        const maxSuitLength = Math.max(...Object.values(suits));
        if (maxSuitLength >= 4) sunScore += 10;  // Long suit is good for control

        return { hokumScore, sunScore };
    }

    /**
     * Evaluate a specific suit as potential Hokum
     */
    evaluateSuitAsHokum(hand, suit) {
        const suitCards = hand.filter(c => c.suit === suit);
        let score = suitCards.length * 12;

        if (suitCards.some(c => c.rank === 'J')) score += 25;
        if (suitCards.some(c => c.rank === '9')) score += 18;
        if (suitCards.some(c => c.rank === 'A')) score += 8;

        return score;
    }

    /**
     * Decide which card to play
     * Strategy: Context-aware decision making
     */
    async decideCard(trickState, legalCards) {
        const { currentTrick, trumpSuit, gameType, trickNumber } = trickState;
        const partnerIndex = (this.playerIndex + 2) % 4;

        // Leading
        if (currentTrick.length === 0) {
            return this.decideLead(legalCards, trumpSuit, gameType, trickNumber);
        }

        // Following
        const ledSuit = currentTrick[0].card.suit;
        const currentWinner = this.getCurrentWinner(currentTrick, trumpSuit, gameType);
        const partnerIsWinning = currentWinner && currentWinner.playerIndex === partnerIndex;

        // Partner winning - play lowest to not waste cards
        if (partnerIsWinning) {
            return this.getLowestCard(legalCards, gameType, false);
        }

        // Calculate trick value to decide how hard to fight
        const trickValue = currentTrick.reduce((sum, play) =>
            sum + play.card.getPointValue(gameType, play.card.suit === trumpSuit), 0
        );

        // Find cards that can win
        const winningCards = legalCards.filter(card =>
            this.cardBeats(card, currentWinner.card, ledSuit, trumpSuit, gameType)
        );

        // High-value trick (15+ points) - try harder to win
        if (winningCards.length > 0 && trickValue >= 15) {
            return this.getLowestCard(winningCards, gameType, legalCards[0]?.suit === trumpSuit);
        }

        // Can win but low value - still win but conserve
        if (winningCards.length > 0) {
            return this.getLowestCard(winningCards, gameType, legalCards[0]?.suit === trumpSuit);
        }

        // Can't win - dump lowest point card
        return this.getLowestPointCard(legalCards, gameType, trumpSuit);
    }

    /**
     * Decide which card to lead with
     * Strategy varies based on game phase
     */
    decideLead(cards, trumpSuit, gameType, trickNumber) {
        const isLateGame = trickNumber >= 6;

        // Late game with trump: lead trump to extract remaining
        if (isLateGame && trumpSuit) {
            const trumps = cards.filter(c => c.suit === trumpSuit);
            // Lead trump if few remain in play
            if (trumps.length > 0 && this.suitCounts[trumpSuit] <= 3) {
                return this.getHighestCard(trumps, gameType, true);
            }
        }

        // Find suit where we have control
        const suitGroups = {};
        for (const card of cards) {
            if (!suitGroups[card.suit]) suitGroups[card.suit] = [];
            suitGroups[card.suit].push(card);
        }

        let bestLead = cards[0];
        let bestScore = -Infinity;

        for (const [suit, suitCards] of Object.entries(suitGroups)) {
            if (suit === trumpSuit) continue;  // Don't lead trump early

            const remainingInSuit = this.suitCounts[suit];
            const highCard = this.getHighestCard(suitCards, gameType, false);

            // Score based on card strength vs remaining cards
            let score = highCard.getRankingPower(gameType, false) * 10;
            score -= remainingInSuit * 5;  // Penalty for many remaining

            // Bonus for Ace (likely to win)
            if (highCard.rank === 'A') score += 20;

            if (score > bestScore) {
                bestScore = score;
                bestLead = highCard;
            }
        }

        // If only trump available, lead highest
        if (bestLead === cards[0] && trumpSuit && cards.every(c => c.suit === trumpSuit)) {
            return this.getHighestCard(cards, gameType, true);
        }

        return bestLead;
    }

    /**
     * Get highest card by ranking
     */
    getHighestCard(cards, gameType, isTrump) {
        return cards.reduce((best, card) =>
            card.getRankingPower(gameType, isTrump) > best.getRankingPower(gameType, isTrump)
                ? card : best
        );
    }

    /**
     * Get lowest card by ranking
     */
    getLowestCard(cards, gameType, isTrump) {
        return cards.reduce((lowest, card) =>
            card.getRankingPower(gameType, isTrump) < lowest.getRankingPower(gameType, isTrump)
                ? card : lowest
        );
    }

    /**
     * Get lowest card by point value (for dumping)
     */
    getLowestPointCard(cards, gameType, trumpSuit) {
        return cards.reduce((lowest, card) => {
            const cardPoints = card.getPointValue(gameType, card.suit === trumpSuit);
            const lowestPoints = lowest.getPointValue(gameType, lowest.suit === trumpSuit);
            return cardPoints < lowestPoints ? card : lowest;
        });
    }

    /**
     * Find current winner of the trick
     */
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

    /**
     * Check if card A beats card B
     */
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

    /**
     * Track cards as they're played
     */
    onCardPlayed(playerIndex, card) {
        this.playedCards.push({ playerIndex, card });
        this.suitCounts[card.suit]--;
    }

    /**
     * Optional: React to trick results
     */
    onTrickWon(winnerIndex, trickCards) {
        // Could update strategy based on who won
        // For example, track if opponents are strong in certain suits
    }
}
