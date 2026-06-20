/**
 * GreedyAI - Team 1 Default Agent
 *
 * Strategy: Simple heuristic-based AI
 * - Bids Hokum with strong trump hands (3+ cards with J or 9)
 * - Bids Sun with many high cards (5+ Aces, 10s, Kings)
 * - Plays highest winning card when possible
 * - Plays lowest card when partner is winning
 *
 * This file can be loaded via the AI Upload feature to test the loading mechanism.
 *
 * @author DS-AI Course
 * @version 1.0.0
 */

class CustomAgent extends BalootAIAgent {
    constructor(playerIndex, teamIndex) {
        super(playerIndex, teamIndex);
        this.name = 'GreedyAI';
        this.version = '1.0.0';
        this.hand = [];
        this.playedCards = new Set();
    }

    /**
     * Called when a new round starts
     */
    onRoundStart(roundInfo) {
        this.playedCards.clear();
    }

    /**
     * Called when receiving cards
     */
    onReceiveHand(hand) {
        this.hand = [...hand];
    }

    /**
     * Decide what to bid
     * Strategy:
     * - Round 1: Compare Hokum vs Sun scores, pick stronger option
     * - Round 2: Evaluate Hokum Thani, Ashkal, and Sun in priority order
     */
    async decideBid(biddingState) {
        const { biddingCard, biddingRound } = biddingState;
        const hand = this.hand;
        const biddingCardSuit = biddingCard.suit;

        if (biddingRound === 1) {
            // Calculate Hokum score
            const trumpCards = hand.filter(c => c.suit === biddingCardSuit);
            let hokumScore = trumpCards.length * 10;  // 10 points per trump card
            if (trumpCards.some(c => c.rank === 'J')) hokumScore += 20;  // Jack bonus
            if (trumpCards.some(c => c.rank === '9')) hokumScore += 15;  // Nine bonus
            if (trumpCards.some(c => c.rank === 'A')) hokumScore += 5;   // Ace bonus

            // Calculate Sun score
            const aces = hand.filter(c => c.rank === 'A').length;
            const tens = hand.filter(c => c.rank === '10').length;
            const kings = hand.filter(c => c.rank === 'K').length;
            let sunScore = aces * 12 + tens * 8 + kings * 5;

            // Greedy thresholds
            const HOKUM_THRESHOLD = 40;
            const SUN_THRESHOLD = 45;

            // Pick the stronger option above threshold
            if (hokumScore >= HOKUM_THRESHOLD && hokumScore >= sunScore) {
                return { bidType: BID_TYPES.HOKUM };
            }
            if (sunScore >= SUN_THRESHOLD && sunScore > hokumScore) {
                return { bidType: BID_TYPES.SUN };
            }

            return { bidType: BID_TYPES.PASS };

        } else {
            // Round 2: Evaluate Hokum Thani, Ashkal, and Sun

            // 1. Evaluate all alternative suits for Hokum Thani
            let bestSuit = null;
            let bestScore = 0;

            for (const suit of Object.values(SUITS)) {
                if (suit === biddingCardSuit) continue;  // Skip bidding card suit

                const suitCards = hand.filter(c => c.suit === suit);
                let score = suitCards.length * 10;  // 10 per card

                if (suitCards.some(c => c.rank === 'J')) score += 20;  // Jack
                if (suitCards.some(c => c.rank === '9')) score += 15;  // Nine
                if (suitCards.some(c => c.rank === 'A')) score += 5;   // Ace

                if (score > bestScore) {
                    bestScore = score;
                    bestSuit = suit;
                }
            }

            // Greedy threshold for Hokum Thani: 35 (lower than round 1)
            if (bestScore >= 35 && bestSuit) {
                return { bidType: BID_TYPES.HOKUM_SECOND, suitChoice: bestSuit };
            }

            // 2. Check if Ashkal (Sun with card transfer) is better
            const aces = hand.filter(c => c.rank === 'A').length;
            const tens = hand.filter(c => c.rank === '10').length;
            const kings = hand.filter(c => c.rank === 'K').length;

            let ashkalScore = aces * 12 + tens * 8 + kings * 5;

            // Penalty: Ashkal means losing the bidding card
            const hasBiddingCard = hand.some(c => c.id === biddingCard.id);
            if (hasBiddingCard) {
                // Subtract value of bidding card from score
                const cardValue = ['A', '10', 'K'].includes(biddingCard.rank) ? 10 : 5;
                ashkalScore -= cardValue;
            }

            // Greedy threshold: 40 (higher than round 1 Sun because of card loss)
            if (ashkalScore >= 40) {
                return { bidType: BID_TYPES.ASHKAL };
            }

            // 3. Otherwise check Sun (lower threshold in round 2)
            const sunScore = aces * 12 + tens * 8 + kings * 5;
            if (sunScore >= 35) {
                return { bidType: BID_TYPES.SUN };
            }

            return { bidType: BID_TYPES.PASS };
        }
    }

    /**
     * Decide whether to double opponent's bid or accept a double
     * Strategy: Evaluate hand strength against thresholds
     */
    async decideDouble(gameState) {
        const { round, players } = gameState;
        const myTeam = this.teamIndex;
        const buyingTeam = round.buyingTeam;
        const hand = players[this.playerIndex].hand;
        const trumpSuit = round.trumpSuit;
        const gameType = round.gameType;

        let handStrength = 0;

        if (gameType === 'hokum' && trumpSuit) {
            // Count trump strength
            const trumpCards = hand.filter(c => c.suit === trumpSuit);
            handStrength = trumpCards.length * 8;
            if (trumpCards.some(c => c.rank === 'J')) handStrength += 15;
            if (trumpCards.some(c => c.rank === '9')) handStrength += 12;
            if (trumpCards.some(c => c.rank === 'A')) handStrength += 8;
        } else {
            // Sun game - count high cards
            const aces = hand.filter(c => c.rank === 'A').length;
            const tens = hand.filter(c => c.rank === '10').length;
            handStrength = aces * 10 + tens * 6;
        }

        const currentLevel = round.doubleLevel;

        // Opponent team doubling
        if (buyingTeam !== myTeam) {
            // Challenge opponent's bid
            const DOUBLE_THRESHOLD = 50;
            const REDOUBLE_THRESHOLD = 55;
            const QUAD_THRESHOLD = 70;

            if (currentLevel === 0 && handStrength >= DOUBLE_THRESHOLD) {
                return true;  // Double to 2x
            }
            if (currentLevel === 1 && handStrength >= REDOUBLE_THRESHOLD) {
                return true;  // Redouble to 3x
            }
            if (currentLevel === 2 && handStrength >= QUAD_THRESHOLD) {
                return true;  // Quadruple to 4x
            }
        } else {
            // Buyer team accepting double
            const ACCEPT_THRESHOLD = 45;
            const ACCEPT_REDOUBLE_THRESHOLD = 55;

            if (currentLevel === 1 && handStrength >= ACCEPT_THRESHOLD) {
                return true;  // Accept double, go to 3x
            }
            if (currentLevel === 2 && handStrength >= ACCEPT_REDOUBLE_THRESHOLD) {
                return true;  // Accept redouble, go to 4x
            }
        }

        return false;  // Don't double
    }

    /**
     * Decide which card to play
     * Strategy:
     * - When leading: play highest non-trump, or highest trump
     * - When following: try to win with lowest winning card
     * - When partner winning: play lowest card
     */
    async decideCard(trickState, legalCards) {
        const { currentTrick, trumpSuit, gameType } = trickState;
        const partnerIndex = (this.playerIndex + 2) % 4;

        // Leading
        if (currentTrick.length === 0) {
            // Lead with highest non-trump if possible
            const nonTrump = legalCards.filter(c => c.suit !== trumpSuit);
            if (nonTrump.length > 0) {
                return this.getHighestCard(nonTrump, gameType, false);
            }
            // Otherwise lead with highest trump
            return this.getHighestCard(legalCards, gameType, true);
        }

        // Following
        const ledSuit = currentTrick[0].card.suit;
        const currentWinner = this.getCurrentWinner(currentTrick, trumpSuit, gameType);
        const partnerIsWinning = currentWinner && currentWinner.playerIndex === partnerIndex;

        // Partner is winning - play lowest card
        if (partnerIsWinning) {
            return this.getLowestCard(legalCards, gameType, ledSuit === trumpSuit);
        }

        // Try to win the trick
        const winningCards = legalCards.filter(card =>
            this.cardBeats(card, currentWinner.card, ledSuit, trumpSuit, gameType)
        );

        if (winningCards.length > 0) {
            // Win with lowest winning card to preserve high cards
            return this.getLowestCard(winningCards, gameType, legalCards[0]?.suit === trumpSuit);
        }

        // Can't win - play lowest card
        return this.getLowestCard(legalCards, gameType, false);
    }

    /**
     * Get the highest card by ranking power
     */
    getHighestCard(cards, gameType, isTrump) {
        return cards.reduce((best, card) =>
            card.getRankingPower(gameType, isTrump) > best.getRankingPower(gameType, isTrump)
                ? card : best
        );
    }

    /**
     * Get the lowest card by ranking power
     */
    getLowestCard(cards, gameType, isTrump) {
        return cards.reduce((lowest, card) =>
            card.getRankingPower(gameType, isTrump) < lowest.getRankingPower(gameType, isTrump)
                ? card : lowest
        );
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

        // Trump beats non-trump
        if (aIsTrump && !bIsTrump) return true;
        if (!aIsTrump && bIsTrump) return false;

        // Both trump - compare trump ranking
        if (aIsTrump && bIsTrump) {
            return cardA.getRankingPower(gameType, true) > cardB.getRankingPower(gameType, true);
        }

        // Non-trump: led suit beats off-suit
        const aIsLed = cardA.suit === ledSuit;
        const bIsLed = cardB.suit === ledSuit;

        if (aIsLed && !bIsLed) return true;
        if (!aIsLed && bIsLed) return false;

        // Same suit - compare normal ranking
        if (cardA.suit === cardB.suit) {
            return cardA.getRankingPower(gameType, false) > cardB.getRankingPower(gameType, false);
        }

        return false;
    }

    /**
     * Track played cards
     */
    onCardPlayed(playerIndex, card) {
        this.playedCards.add(card.id);
    }
}
