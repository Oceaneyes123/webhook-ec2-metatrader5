# ADR: RSI extreme alerts use a continuation bias

- Status: Accepted
- Date: 2026-09-16

## Context

An RSI extreme alone does not reliably signal a reversal. Strong momentum often
continues beyond an overbought or oversold reading; a divergence is the first
required reversal warning.

## Decision

Telegram's informational RSI alerts use continuation direction:

- RSI overbought (>= 75): BUY.
- RSI oversold (<= 25): SELL.

The alert tells the trader to wait for an RSI divergence before treating the
extreme as a reversal opportunity. Existing divergence alerts remain the
reversal signal; this decision does not place or modify trades automatically.

## Consequences

Extreme-RSI notifications align with momentum rather than countertrend entries.
Traders must still apply their normal trend, location, confirmation, risk, and
trade-management rules.
