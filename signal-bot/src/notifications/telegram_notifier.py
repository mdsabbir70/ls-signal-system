"""
Telegram Notifier
Sends signal alerts and daily summaries to configured Telegram chat.

Messages:
  - Signal Open  (with emoji, entry/SL/TP, lot size, score)
  - Signal Close (TP hit / SL hit / Manual)
  - Daily Summary
  - Error alerts
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta

# Bangladesh Standard Time (UTC+6)
BDT = timezone(timedelta(hours=6), 'BDT')
from typing import Optional

from utils.logger import setup_logger

logger = setup_logger('telegram')


class TelegramNotifier:
    """Sends Telegram messages via Bot API."""

    def __init__(self, config):
        self.config = config
        self._bot = None
        self._chat_id = None
        self._init()

    def _init(self):
        """Initialize Telegram bot."""
        token   = self.config.TELEGRAM_BOT_TOKEN
        chat_id = self.config.TELEGRAM_CHAT_ID

        if not token or not chat_id:
            logger.warning("Telegram credentials not configured")
            return

        try:
            from telegram import Bot
            self._bot     = Bot(token=token)
            self._chat_id = chat_id
            logger.info("Telegram bot initialized")
        except ImportError:
            logger.warning("python-telegram-bot not installed — pip install python-telegram-bot")
        except Exception as e:
            logger.error(f"Telegram init failed: {e}")

    async def send_signal(self, signal: dict) -> Optional[int]:
        """Send signal open notification. Returns Telegram message ID."""
        if not self._bot:
            return None

        msg = self._format_signal(signal)
        return await self._send(msg)

    async def send_signal_close(self, signal: dict, close_data: dict) -> Optional[int]:
        """Send signal close notification (TP/SL/Manual)."""
        if not self._bot:
            return None

        msg = self._format_close(signal, close_data)
        return await self._send(msg)

    async def send_daily_summary(self, stats: dict) -> Optional[int]:
        """Send daily performance summary."""
        if not self._bot:
            return None

        msg = self._format_daily_summary(stats)
        return await self._send(msg)

    async def send_weekly_summary(self, stats: dict) -> Optional[int]:
        """Send weekly performance summary."""
        if not self._bot:
            return None
        msg = self._format_weekly_summary(stats)
        return await self._send(msg)

    async def send_monthly_summary(self, stats: dict) -> Optional[int]:
        """Send monthly performance summary."""
        if not self._bot:
            return None
        msg = self._format_monthly_summary(stats)
        return await self._send(msg)

    async def send_error(self, message: str) -> Optional[int]:
        """Send error alert."""
        if not self._bot:
            return None

        msg = f"🚨 <b>LS Signal Bot Error</b>\n\n<code>{self._esc(message)}</code>"
        return await self._send(msg)

    async def _send(self, text: str) -> Optional[int]:
        """Send a message and return the message ID."""
        if not self._bot or not self._chat_id:
            return None
        try:
            msg = await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True,
            )
            return msg.message_id
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return None

    # ── Message formatters ─────────────────────────────────────────────────

    @staticmethod
    def _esc(text) -> str:
        """Escape HTML special characters."""
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    @classmethod
    def _format_signal(cls, signal: dict) -> str:
        direction = signal['direction']
        pair      = signal['pair']
        quality   = signal.get('quality_label', '?')
        score     = signal.get('confluence_score', 0)

        dir_emoji  = '🟢' if direction == 'BUY' else '🔴'
        qual_emoji = {'A+': '⭐⭐⭐', 'A': '⭐⭐', 'B': '⭐', 'C': '▪️', 'D': '⚠️'}.get(quality, '')

        htf_trend = cls._esc(str(signal.get('htf_trend', 'N/A')).replace('_', ' '))
        regime    = cls._esc(str(signal.get('market_regime', 'N/A')).replace('_', ' '))

        lines = [
            f"{dir_emoji} <b>{direction} {pair}</b>  {qual_emoji}",
            f"",
            f"📊 <b>Signal ID:</b> <code>{cls._esc(signal.get('signal_id', 'N/A'))}</code>",
            f"💡 <b>Mode:</b> {cls._esc(signal.get('mode', 'hybrid').upper())}",
            f"🎯 <b>Confluence Score:</b> {score:.1f}/100 ({quality})",
            f"",
            f"📈 <b>Entry:</b> <code>{signal.get('entry_price', 0):.5f}</code>",
            f"🛑 <b>Stop Loss:</b> <code>{signal.get('stop_loss', 0):.5f}</code> ({signal.get('sl_pips', 0):.0f} pips)",
            f"✅ <b>Take Profit:</b> <code>{signal.get('take_profit', 0):.5f}</code> ({signal.get('tp_pips', 0):.0f} pips)",
            f"⚖️ <b>R:R Ratio:</b> 1:{signal.get('risk_reward_ratio', 0):.1f}",
            f"",
            f"📦 <b>Lot Size:</b> {signal.get('suggested_lot', 0):.2f}",
            f"💵 <b>Risk:</b> ${signal.get('risk_amount', 0):.2f}",
            f"",
            f"🕐 <b>Timeframe:</b> {cls._esc(signal.get('timeframe', 'H1'))}",
            f"📊 <b>HTF Trend:</b> {htf_trend}",
            f"📊 <b>Market Regime:</b> {regime}",
        ]

        news_sentiment = signal.get('news_sentiment', 'neutral')
        if news_sentiment != 'neutral':
            sentiment_emoji = '📰🟢' if news_sentiment == 'bullish' else '📰🔴'
            lines.append(f"{sentiment_emoji} <b>News Sentiment:</b> {news_sentiment.upper()}")

        # ── Candlestick Patterns ─────────────────────────────────────
        candle_sum = signal.get('candlestick_summary', '')
        if candle_sum:
            lines.extend([
                f"",
                f"🕯 <b>Candlestick:</b> {cls._esc(candle_sum)}",
            ])

        # ── Liquidity / Smart Money Concepts ─────────────────────────
        liq = signal.get('liquidity_summary', '')
        if liq:
            lines.extend([
                f"",
                f"🏦 <b>Smart Money:</b> {cls._esc(liq)}",
            ])

        # Breakdown with liquidity
        bd = signal.get('score_breakdown', {})
        liq_score = bd.get('liquidity', 0)
        if liq_score:
            detail = bd.get('detail', {})
            liq_parts = []
            if detail.get('order_block', 0) > 0:
                liq_parts.append(f"OB {detail['order_block']:.0f}")
            if detail.get('fvg', 0) > 0:
                liq_parts.append(f"FVG {detail['fvg']:.0f}")
            if detail.get('market_structure', 0) > 0:
                liq_parts.append(f"Struct {detail['market_structure']:.0f}")
            if detail.get('liquidity_sweep', 0) > 0:
                liq_parts.append(f"Sweep {detail['liquidity_sweep']:.0f}")
            if liq_parts:
                lines.append(f"📐 <b>SMC Score:</b> {liq_score:.0f}/20 ({', '.join(liq_parts)})")

        # Candlestick score in breakdown
        detail = bd.get('detail', {})
        candle_score = detail.get('candlestick', 0)
        if candle_score > 0:
            lines.append(f"🕯 <b>Candle Score:</b> {candle_score:.0f}/6")

        # ── Session / Kill Zone ────────────────────────────────────────
        session_info = signal.get('session_info', {})
        session_quality = signal.get('session_quality', '')
        kill_zone = signal.get('kill_zone', '')

        if session_info:
            active = session_info.get('active_sessions', [])
            if active:
                sess_str = ', '.join(s.capitalize() for s in active)
                qual_emoji = {'optimal': '🟢', 'acceptable': '🟡', 'poor': '🔴'}.get(session_quality, '')
                lines.append(f"")
                lines.append(f"🌍 <b>Session:</b> {cls._esc(sess_str)} {qual_emoji}")

            if session_info.get('in_overlap'):
                lines.append(f"🔥 <b>Overlap:</b> {cls._esc(session_info.get('overlap', 'Session overlap'))}")

        if kill_zone:
            lines.append(f"🎯 <b>Kill Zone:</b> {cls._esc(kill_zone)}")

        # Session/correlation/sentiment modifiers
        detail = bd.get('detail', {})
        sess_mod = detail.get('session_modifier', 0)
        corr_mod = detail.get('correlation_modifier', 0)
        sent_mod_val = detail.get('sentiment_modifier', 0)
        if sess_mod != 0 or corr_mod != 0 or sent_mod_val != 0:
            mod_parts = []
            if sess_mod != 0:
                mod_parts.append(f"Session {'+' if sess_mod > 0 else ''}{sess_mod:.1f}")
            if corr_mod != 0:
                mod_parts.append(f"Correlation {'+' if corr_mod > 0 else ''}{corr_mod:.1f}")
            if sent_mod_val != 0:
                mod_parts.append(f"Sentiment {'+' if sent_mod_val > 0 else ''}{sent_mod_val:.1f}")
            lines.append(f"📊 <b>Modifiers:</b> {', '.join(mod_parts)}")

        # Correlation info
        corr_data = signal.get('correlation', {})
        if corr_data and corr_data.get('action') == 'WARN':
            lines.append(f"⚠️ <b>Correlation:</b> {cls._esc(corr_data.get('reason', ''))}")
        elif corr_data and corr_data.get('confirmation_boost', 0) > 0:
            lines.append(f"✅ <b>Cross-pair confirmation:</b> +{corr_data['confirmation_boost']:.1f}")

        # ── Economic Calendar ─────────────────────────────────────────
        econ_gate = signal.get('econ_gate', '')
        if econ_gate == 'CAUTION':
            lines.append(f"⚡ <b>Econ Alert:</b> High-impact event nearby — trade with caution")

        econ_bias = signal.get('econ_bias', {})
        if econ_bias and econ_bias.get('bias', 'neutral') != 'neutral':
            bias_emoji = '📈' if econ_bias['bias'] == 'bullish' else '📉'
            lines.append(f"{bias_emoji} <b>Econ Bias:</b> {cls._esc(econ_bias['bias'].upper())} — {cls._esc(econ_bias.get('reason', ''))}")

        # ── Market Sentiment ──────────────────────────────────────────
        sent_data = signal.get('sentiment_data', {})
        if sent_data and sent_data.get('overall_sentiment', 'neutral') != 'neutral':
            sent_label = sent_data.get('overall_sentiment', '').replace('_', ' ').upper()
            sent_emojis = {
                'EXTREME FEAR': '😨', 'FEAR': '😰',
                'GREED': '🤑', 'EXTREME GREED': '🤩',
            }
            sent_emoji = sent_emojis.get(sent_label, '📊')

            lines.append(f"")
            lines.append(f"{sent_emoji} <b>Sentiment:</b> {cls._esc(sent_label)}")

            # Show source details
            fng = sent_data.get('fear_greed_value', 0)
            if fng > 0:
                lines.append(f"📊 <b>Fear &amp; Greed:</b> {fng}/100 ({cls._esc(sent_data.get('fear_greed_label', ''))})")

            vix = sent_data.get('vix_value', 0)
            if vix > 0:
                lines.append(f"📉 <b>VIX:</b> {vix:.1f} ({cls._esc(sent_data.get('vix_label', ''))})")

            sent_mod = sent_data.get('score_modifier', 0)
            if sent_mod != 0:
                mod_emoji = '📈' if sent_mod > 0 else '📉'
                lines.append(f"{mod_emoji} <b>Sent. Modifier:</b> {'+' if sent_mod > 0 else ''}{sent_mod:.1f}")

            if sent_data.get('contrarian_signal'):
                lines.append(f"🔄 <b>Contrarian Signal Active</b>")

            if sent_data.get('risk_adjustment') == 'reduce':
                lines.append(f"⚠️ <b>Risk:</b> Reduced position recommended")

        # ── AI Trade Brain ────────────────────────────────────────────
        ai_v = signal.get('ai_verdict', {})
        if ai_v and ai_v.get('verdict'):
            verdict = ai_v['verdict']
            v_emoji = {
                'STRONG_BUY': '🧠🟢🟢', 'BUY': '🧠🟢',
                'NEUTRAL': '🧠⚪', 'SELL': '🧠🔴',
                'STRONG_SELL': '🧠🔴🔴',
            }.get(verdict, '🧠')
            lines.extend([
                f"",
                f"{v_emoji} <b>AI Brain:</b> {cls._esc(verdict)} ({ai_v.get('confidence', 0):.0f}%)",
            ])
            reasoning = ai_v.get('reasoning', '')
            if reasoning:
                lines.append(f"<i>{cls._esc(reasoning[:300])}</i>")
            risk = ai_v.get('risk_level', '')
            if risk:
                risk_emoji = {'LOW': '🟢', 'MEDIUM': '🟡', 'HIGH': '🔴'}.get(risk, '')
                lines.append(f"{risk_emoji} <b>Risk:</b> {cls._esc(risk)}")
            factors = ai_v.get('key_factors', [])
            if factors:
                lines.append(f"📋 <b>Key:</b> {cls._esc(', '.join(factors[:3]))}")
            context = ai_v.get('market_context', '')
            if context:
                lines.append(f"📌 {cls._esc(context)}")

        lines.extend([
            f"",
            f"⏰ {datetime.now(BDT).strftime('%d %b %Y, %I:%M %p')} BDT",
            f"",
            f"⚠️ <i>This is a signal only. Always verify before trading.</i>",
        ])

        return "\n".join(lines)

    @classmethod
    def _format_close(cls, signal: dict, close_data: dict) -> str:
        status = close_data.get('status', '')
        pair   = signal.get('pair', '')
        actual_pips   = close_data.get('actual_pips', 0)
        actual_profit = close_data.get('actual_profit', 0)

        if status == 'CLOSED_TP':
            icon = '✅'
            result = f"+{actual_pips:.0f} pips (+${actual_profit:.2f})"
        elif status == 'CLOSED_SL':
            icon = '🛑'
            result = f"-{abs(actual_pips):.0f} pips (-${abs(actual_profit):.2f})"
        else:
            icon = '🔄'
            result = f"{actual_pips:.0f} pips"

        lines = [
            f"{icon} <b>{cls._esc(pair)} Signal Closed</b>",
            f"",
            f"📊 <b>Signal:</b> <code>{cls._esc(signal.get('signal_id', 'N/A'))}</code>",
            f"📌 <b>Result:</b> {cls._esc(result)}",
            f"⏱ <b>Duration:</b> {close_data.get('duration_minutes', 0)} minutes",
            f"🔚 <b>Close Price:</b> <code>{close_data.get('close_price', 0):.5f}</code>",
            f"📝 <b>Reason:</b> {cls._esc(close_data.get('close_reason', status))}",
            f"",
            f"⏰ {datetime.now(BDT).strftime('%d %b %Y, %I:%M %p')} BDT",
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_daily_summary(stats: dict) -> str:
        win_rate  = stats.get('win_rate', 0)
        net_pips  = stats.get('net_pips', 0)
        net_pnl   = stats.get('net_pnl', 0)
        total     = stats.get('total_signals', 0)
        tp_hits   = stats.get('closed_tp', 0)
        sl_hits   = stats.get('closed_sl', 0)
        pf        = stats.get('profit_factor', 0)

        pnl_emoji = '📈' if net_pnl >= 0 else '📉'
        pnl_sign  = '+' if net_pnl >= 0 else ''

        lines = [
            f"📊 <b>LS Signal — Daily Summary</b>",
            f"📅 {stats.get('stat_date', 'Today')}",
            f"",
            f"📋 <b>Signals:</b> {total}  |  ✅ {tp_hits}  |  🛑 {sl_hits}",
            f"🎯 <b>Win Rate:</b> {win_rate:.1f}%",
            f"📐 <b>Profit Factor:</b> {pf:.2f}",
            f"",
            f"💰 <b>Net Pips:</b> {'+' if net_pips >= 0 else ''}{net_pips:.0f}",
            f"{pnl_emoji} <b>Net P&amp;L:</b> {pnl_sign}${net_pnl:.2f}",
            f"",
            f"<i>signal.lstrading.xyz</i>",
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_weekly_summary(stats: dict) -> str:
        win_rate  = stats.get('win_rate', 0)
        net_pips  = stats.get('net_pips', 0)
        net_pnl   = stats.get('net_pnl', 0)
        total     = stats.get('total_signals', 0)
        tp_hits   = stats.get('closed_tp', 0)
        sl_hits   = stats.get('closed_sl', 0)
        pf        = stats.get('profit_factor', 0)
        best_pair = stats.get('best_pair', 'N/A')
        worst_pair = stats.get('worst_pair', 'N/A')

        pnl_emoji = '📈' if net_pnl >= 0 else '📉'
        pnl_sign  = '+' if net_pnl >= 0 else ''

        lines = [
            f"📊 <b>LS Signal — Weekly Report</b>",
            f"📅 {stats.get('week_start', '')} — {stats.get('week_end', '')}",
            f"",
            f"📋 <b>Total Signals:</b> {total}",
            f"✅ <b>TP Hits:</b> {tp_hits}  |  🛑 <b>SL Hits:</b> {sl_hits}",
            f"🎯 <b>Win Rate:</b> {win_rate:.1f}%",
            f"📐 <b>Profit Factor:</b> {pf:.2f}",
            f"",
            f"💰 <b>Net Pips:</b> {'+' if net_pips >= 0 else ''}{net_pips:.0f}",
            f"{pnl_emoji} <b>Net P&amp;L:</b> {pnl_sign}${net_pnl:.2f}",
            f"",
            f"🏆 <b>Best Pair:</b> {best_pair}",
            f"💀 <b>Worst Pair:</b> {worst_pair}",
            f"",
            f"<i>signal.lstrading.xyz</i>",
        ]
        return "\n".join(lines)

    @staticmethod
    def _format_monthly_summary(stats: dict) -> str:
        win_rate  = stats.get('win_rate', 0)
        net_pips  = stats.get('net_pips', 0)
        net_pnl   = stats.get('net_pnl', 0)
        total     = stats.get('total_signals', 0)
        tp_hits   = stats.get('closed_tp', 0)
        sl_hits   = stats.get('closed_sl', 0)
        pf        = stats.get('profit_factor', 0)
        best_pair = stats.get('best_pair', 'N/A')
        trading_days = stats.get('trading_days', 0)

        pnl_emoji = '📈' if net_pnl >= 0 else '📉'
        pnl_sign  = '+' if net_pnl >= 0 else ''

        lines = [
            f"📊 <b>LS Signal — Monthly Report</b>",
            f"📅 {stats.get('month_label', '')}",
            f"",
            f"📋 <b>Total Signals:</b> {total} ({trading_days} trading days)",
            f"✅ <b>TP Hits:</b> {tp_hits}  |  🛑 <b>SL Hits:</b> {sl_hits}",
            f"🎯 <b>Win Rate:</b> {win_rate:.1f}%",
            f"📐 <b>Profit Factor:</b> {pf:.2f}",
            f"",
            f"💰 <b>Net Pips:</b> {'+' if net_pips >= 0 else ''}{net_pips:.0f}",
            f"{pnl_emoji} <b>Net P&amp;L:</b> {pnl_sign}${net_pnl:.2f}",
            f"",
            f"🏆 <b>Best Pair:</b> {best_pair}",
        ]
        if trading_days > 0:
            lines.append(f"📊 <b>Avg/Day:</b> {(total/trading_days):.1f} signals")
        lines.extend([f"", f"<i>signal.lstrading.xyz</i>"])
        return "\n".join(lines)
