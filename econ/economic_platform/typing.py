from __future__ import annotations

from enum import Enum


class ActionType(Enum):
    EXIT                 = "exit"
    REGISTER             = "register"
    OBSERVE_MARKET       = "observe_market"
    PRODUCE              = "produce"
    REFINE               = "refine"
    LIST_GOOD            = "list_good"
    UPDATE_LISTING_PRICE = "update_listing_price"
    PLACE_BID            = "place_bid"
    CHECK_BALANCE        = "check_balance"
    CHECK_PRICE_HISTORY  = "check_price_history"
    REQUEST_LOAN         = "request_loan"
    APPROVE_LOAN         = "approve_loan"
    DENY_LOAN            = "deny_loan"
    REPAY                = "repay"
    SEARCH_GOODS         = "search_goods"
    SEARCH_AGENTS        = "search_agents"
    DO_NOTHING           = "do_nothing"
    INTERVIEW            = "interview"

    @classmethod
    def get_firm_actions(cls) -> list[ActionType]:
        return [
            cls.OBSERVE_MARKET,
            cls.PRODUCE,
            cls.LIST_GOOD,
            cls.UPDATE_LISTING_PRICE,
            cls.CHECK_BALANCE,
            cls.CHECK_PRICE_HISTORY,
            cls.REQUEST_LOAN,
            cls.REPAY,
            cls.DO_NOTHING,
        ]

    @classmethod
    def get_consumer_actions(cls) -> list[ActionType]:
        return [
            cls.OBSERVE_MARKET,
            cls.PLACE_BID,
            cls.CHECK_BALANCE,
            cls.CHECK_PRICE_HISTORY,
            cls.SEARCH_GOODS,
            cls.REQUEST_LOAN,
            cls.REPAY,
            cls.DO_NOTHING,
        ]

    @classmethod
    def get_bank_actions(cls) -> list[ActionType]:
        """Adjudicate credit: observe applicants, then approve/deny per request."""
        return [
            cls.OBSERVE_MARKET,
            cls.CHECK_BALANCE,
            cls.CHECK_PRICE_HISTORY,
            cls.SEARCH_AGENTS,
            cls.APPROVE_LOAN,
            cls.DENY_LOAN,
            cls.DO_NOTHING,
        ]

    @classmethod
    def get_refiner_actions(cls) -> list[ActionType]:
        """Buy crude inputs, refine them into products, and list output."""
        return [
            cls.OBSERVE_MARKET,
            cls.PLACE_BID,
            cls.SEARCH_GOODS,
            cls.REFINE,
            cls.LIST_GOOD,
            cls.UPDATE_LISTING_PRICE,
            cls.CHECK_BALANCE,
            cls.CHECK_PRICE_HISTORY,
            cls.REQUEST_LOAN,
            cls.REPAY,
            cls.DO_NOTHING,
        ]

    @classmethod
    def get_speculator_actions(cls) -> list[ActionType]:
        """Buy commodities at low prices and resell when prices rise."""
        return [
            cls.OBSERVE_MARKET,
            cls.PLACE_BID,
            cls.LIST_GOOD,
            cls.SEARCH_GOODS,
            cls.SEARCH_AGENTS,
            cls.CHECK_BALANCE,
            cls.CHECK_PRICE_HISTORY,
            cls.REQUEST_LOAN,
            cls.REPAY,
            cls.DO_NOTHING,
        ]


class MarketType(Enum):
    GOODS_MARKET      = "goods_market"
    LABOR_MARKET      = "labor_market"
    FINANCIAL_MARKET  = "financial_market"


class DefaultEconomyType(Enum):
    SIMPLE_GOODS  = "simple_goods"
    FULL_ECONOMY  = "full_economy"
