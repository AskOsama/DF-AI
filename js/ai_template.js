/**
 * Custom Baloot AI Agent Template
 *
 * INSTRUCTIONS:
 * 1. Rename this file (e.g., my_awesome_ai.js)
 * 2. Implement the decideBid() and decideCard() methods
 * 3. Upload via the "Upload AI" button in the Baloot game
 *
 * IMPORTANT: Keep the class name as "CustomAgent" - the game expects this exact name!
 *
 * Available globals when loaded:
 * - BalootAIAgent: Base class to extend
 * - BID_TYPES: { PASS, HOKUM, SUN, HOKUM_SECOND }
 * - SUITS: { CLUBS, DIAMONDS, HEARTS, SPADES }
 * - SUIT_SYMBOLS: { clubs: '♣', diamonds: '♦', hearts: '♥', spades: '♠' }
 *
 * Card objects have these methods:
 * - card.suit: 'clubs', 'diamonds', 'hearts', or 'spades'
 * - card.rank: '7', '8', '9', '10', 'J', 'Q', 'K', 'A'
 * - card.id: Unique identifier like 'A-spades'
 * - card.getPointValue(gameType, isTrump): Returns point value
 * - card.getRankingPower(gameType, isTrump): Returns ranking (0-7, higher is stronger)
 * - card.getSequenceValue(): Returns sequential value (7-14) for project detection
 *
 * @author Your Name Here
 * @version 1.0.0
 */

class CustomAgent extends BalootAIAgent {
    constructor(playerIndex, teamIndex) {
        super(playerIndex, teamIndex);

        // ====== CUSTOMIZE THESE ======
        this.name = 'My Custom AI';  // Your AI's name (shown in UI)
        this.version = '1.0.0';
        // =============================

        // Your state variables
        this.hand = [];
        this.playedCards = [];
    }

    /**
     * Called when a new round starts
     * Use this to reset your tracking variables
     *
     * @param {object} roundInfo - { dealerIndex: number }
     */
    onRoundStart(roundInfo) {
        this.playedCards = [];
        // Add your round initialization here
    }

    /**
     * Called when you receive your cards (5 cards initially, 8 after bidding)
     *
     * @param {Card[]} hand - Array of Card objects
     */
    onReceiveHand(hand) {
        this.hand = [...hand];
        // Analyze your hand here if needed
    }

    /**
     * REQUIRED: Decide what to bid
     *
     * @param {object} biddingState
     *   - biddingCard: Card object (the face-up card)
     *   - biddingRound: 1 or 2
     *   - bids: Array of previous bids [{playerIndex, bidType, suitChoice}]
     *   - validBids: Array of valid bid types for this turn
     *
     * @returns {Promise<object>} Your bid decision:
     *   - { bidType: 'pass' }
     *   - { bidType: 'hokum' }  (Round 1 only - takes bidding card suit)
     *   - { bidType: 'sun' }
     *   - { bidType: 'hokum2', suitChoice: 'hearts' }  (Round 2 - must be different suit)
     */
    async decideBid(biddingState) {
        const { biddingCard, biddingRound, validBids } = biddingState;

        // ========================================
        // TODO: IMPLEMENT YOUR BIDDING STRATEGY
        // ========================================

        // Example: Simple random bidding (replace with your strategy!)
        if (biddingRound === 1) {
            // Count cards in bidding card suit
            const trumpCount = this.hand.filter(c => c.suit === biddingCard.suit).length;
            const hasJack = this.hand.some(c => c.suit === biddingCard.suit && c.rank === 'J');

            // Bid Hokum if we have 3+ trump cards with Jack
            if (trumpCount >= 3 && hasJack && validBids.includes('hokum')) {
                return { bidType: 'hokum' };
            }

            // Otherwise pass
            return { bidType: 'pass' };

        } else {
            // Round 2: Choose best alternative suit for Hokum Second
            if (validBids.includes('hokum2')) {
                const suits = ['clubs', 'diamonds', 'hearts', 'spades'];
                const availableSuits = suits.filter(s => s !== biddingCard.suit);

                // Find suit with most cards
                let bestSuit = availableSuits[0];
                let bestCount = 0;
                for (const suit of availableSuits) {
                    const count = this.hand.filter(c => c.suit === suit).length;
                    if (count > bestCount) {
                        bestCount = count;
                        bestSuit = suit;
                    }
                }

                if (bestCount >= 2) {
                    return { bidType: 'hokum2', suitChoice: bestSuit };
                }
            }

            return { bidType: 'pass' };
        }
    }

    /**
     * REQUIRED: Decide which card to play
     *
     * @param {object} trickState
     *   - currentTrick: Array of plays [{playerIndex, card}]
     *   - trumpSuit: 'clubs'/'diamonds'/'hearts'/'spades' or null for Sun
     *   - gameType: 'hokum' or 'sun'
     *   - trickNumber: 1-8
     *
     * @param {Card[]} legalCards - Cards you can legally play
     *
     * @returns {Promise<Card>} The card to play (must be from legalCards!)
     */
    async decideCard(trickState, legalCards) {
        const { currentTrick, trumpSuit, gameType, trickNumber } = trickState;

        // ========================================
        // TODO: IMPLEMENT YOUR CARD PLAY STRATEGY
        // ========================================

        // Example: Simple strategy (replace with your own!)

        // If we're leading (first to play)
        if (currentTrick.length === 0) {
            // Lead with highest non-trump card
            const nonTrump = legalCards.filter(c => c.suit !== trumpSuit);
            if (nonTrump.length > 0) {
                return this.getHighestCard(nonTrump, gameType);
            }
            return this.getHighestCard(legalCards, gameType);
        }

        // If following, just play the first legal card (REPLACE THIS!)
        return legalCards[0];
    }

    /**
     * Optional: Choose which projects to declare
     *
     * @param {object[]} detectedProjects - Projects found in your hand
     *   Each project: { type, cards, points }
     *
     * @returns {Promise<object[]>} Projects to declare (max 2)
     */
    async declareProjects(detectedProjects) {
        // Default: declare highest value projects
        return detectedProjects
            .sort((a, b) => b.points - a.points)
            .slice(0, 2);
    }

    /**
     * Optional: Called when any player plays a card
     * Use this to track what's been played
     *
     * @param {number} playerIndex - Who played (0-3)
     * @param {Card} card - The card that was played
     */
    onCardPlayed(playerIndex, card) {
        this.playedCards.push({ playerIndex, card: card.id });
    }

    /**
     * Optional: Called when a trick is won
     *
     * @param {number} winnerIndex - Who won the trick (0-3)
     * @param {Card[]} trickCards - The 4 cards from the trick
     */
    onTrickWon(winnerIndex, trickCards) {
        // Track results if useful for your strategy
    }

    // ========================================
    // HELPER METHODS (feel free to modify/add)
    // ========================================

    /**
     * Get the highest card by ranking power
     */
    getHighestCard(cards, gameType) {
        let isTrump = false; // Simplified - you may want to check trump suit
        return cards.reduce((best, card) =>
            card.getRankingPower(gameType, isTrump) > best.getRankingPower(gameType, isTrump)
                ? card : best
        );
    }

    /**
     * Get the lowest card by ranking power
     */
    getLowestCard(cards, gameType) {
        let isTrump = false;
        return cards.reduce((lowest, card) =>
            card.getRankingPower(gameType, isTrump) < lowest.getRankingPower(gameType, isTrump)
                ? card : lowest
        );
    }

    /**
     * Count cards in a specific suit
     */
    countSuit(suit) {
        return this.hand.filter(c => c.suit === suit).length;
    }

    /**
     * Check if we have a specific card
     */
    hasCard(suit, rank) {
        return this.hand.some(c => c.suit === suit && c.rank === rank);
    }
}
