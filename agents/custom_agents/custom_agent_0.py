from decimal import Decimal
import logging
from random import randint
from typing import Callable, cast
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive

from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.progress.ProgressRounds import ProgressRounds
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from agents.time_dependent_agent.extended_util_space import ExtendedUtilSpace

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.Profile import Profile
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from utils.frequency_analyzer import FrequencyAnalyzer
from utils.plot_trace import plot_characteristics


class CustomAgent(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self):
        super().__init__()
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profileint: ProfileInterface = None # type:ignore
        self._last_received_bid: Bid = None # type:ignore
        self._utilspace: UtilitySpace = None # type:ignore
        self._extendedspace: ExtendedUtilSpace = None # type:ignore

        # General settings
        self.opponent_model = FrequencyAnalyzer()
        self.reservation_utility: float = .0 # not sure if this is a good value to have, since any agreement is better than no agreement...
        self.falldown_speed: float = 1.2 # < 1: will concede faster; > 1: will concede slower [0.0, ...]
        self.attempts: int = 100 # the number of iterations it will go through to look for an 'optimal' bid
        self.hard_to_get: float = .1 #  the moment from which we'll consider playing nice [0.0, 1.0]
        self.niceness: Decimal = Decimal(.05) # utility we're considering to give up for the sake of being nice [0.0, 1.0]

        # Agent characteristics:
        # Can be included in plotting, make sure the dimensionality of all of them match up
        self.thresholds: list[float] = []

    def notifyChange(self, info: Inform):
        """This is the entry point of all interaction with your agent after is has been initialised.

        Args:
            info (Inform): Contains either a request for action or information.
        """

        # a Settings message is the first message that will be send to your
        # agent containing all the information about the negotiation session.
        if isinstance(info, Settings):
            self._settings: Settings = cast(Settings, info)
            self._me = self._settings.getID()

            # progress towards the deadline has to be tracked manually through the use of the Progress object
            self._progress = self._settings.getProgress()

            # the profile contains the preferences of the agent over the domain
            self._profileint = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )
            self.opponent_model.set_domain(self._profileint.getProfile().getDomain())

            reservation_bid = self._profileint.getProfile().getReservationBid()
            if reservation_bid is not None:
                self.reservation_utility = self._profileint.getProfile().getUtility(reservation_bid)

        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()
        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            # execute a turn
            self._my_turn()

            if isinstance(self._progress, ProgressRounds):
                self._progress = self._progress.advance()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(info, Finished):
            # terminate the agent MUST BE CALLED
            self.terminate()
        else:
            self.getReporter().log(
                logging.WARNING, "Ignoring unknown info " + str(info)
            )

    # lets the geniusweb system know what settings this agent can handle
    # leave it as it is for this course
    def getCapabilities(self) -> Capabilities:
        return Capabilities(
            set(["SAOP"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    # terminates the agent and its connections
    # leave it as it is for this course
    def terminate(self):
        self.getReporter().log(logging.INFO, "party is terminating:")
        self._plot_characteristics()
        super().terminate()
        if self._profileint is not None:
            self._profileint.close()

    # ===================
    # === AGENT LOGIC ===
    # ===================

    # give a description of your agent
    def getDescription(self) -> str:
        return "Shaken, not stirred"

    # execute a turn
    def _my_turn(self):
        self._update_utilspace()
        self.opponent_model.add_bid(self._last_received_bid)
        next_bid = self._find_bid(self.attempts)

        if self._is_acceptable(self._last_received_bid, next_bid):
            action = Accept(self._me, self._last_received_bid)
        else:
            action = Offer(self._me, next_bid)

        # send the action
        self.getConnection().send(action)

    # =================
    # === ACCEPTING ===
    # =================

    # method that checks if we should agree with an incoming offer
    def _is_acceptable(self, bid: Bid, our_next_bid: Bid) -> bool:
        if bid is None:
            return False

        profile, progress = self._get_profile_and_progress()
        bid_utility = profile.getUtility(bid)
        target_bid_utility = profile.getUtility(our_next_bid)

        # TODO non-linear conceding strategy
        threshold = self.falldown_speed * (1.0 - progress) * float(target_bid_utility)
        self.thresholds.append(threshold)

        # Has to be at least more than the reservation value
        return bid_utility > self.reservation_utility and bid_utility > threshold


    # ===============
    # === BIDDING ===
    # ===============

    def _find_bid(self, attempts) -> Bid:
        # compose a list of all possible bids
        _, progress = self._get_profile_and_progress()

        # it the beginning we'll play hard to get
        # after that we'll consider playing nice
        # => this makes us indicate our interests and gives us
        #    the opportunity to collect information about our opponent
        if progress < self.hard_to_get:
            return self._find_max_bid()
        else:
            return self._find_max_nice_bid(attempts)

    def _lower_util_bound(self, our_bid: Bid) -> float:
        profile, progress = self._get_profile_and_progress()

        target_bid_utility = profile.getUtility(our_bid)
        threshold = self.falldown_speed * (1.0 - progress) * float(target_bid_utility)

        return threshold

    """
    Gets a random bid from the given list of all_bids
    """
    def _get_random_bid(self, all_bids: ImmutableList[Bid]):
        return all_bids.get(randint(0, all_bids.size() - 1))

    """
    Finds the maximum bid according to a certain proposition
    """
    def _find_bid_with(self, proposition: Callable[[Bid, Bid], bool], attempts: int):
        # compose a list of all possible bids
        all_bids = AllBidsList(self._profileint.getProfile().getDomain())

        # TODO start with bid which is slightly lower that the max
        # so we can explore more win-win situations
        maxBid = self._find_max_bid()

        # generate an _attempt_ number of bids and get the one with the max utility
        for _ in range(attempts):
            bid = self._get_random_bid(all_bids)
            maxBid = bid if proposition(bid, maxBid) else maxBid

        return maxBid

    """
    Find the maximum bids from the domain
    """
    def _find_max_bid(self) -> Bid:
        max_bids = self._extendedspace.getBids(self._extendedspace.getMax())
        return self._get_random_bid(max_bids)

    """
    Finds the maximum bid while trying to also accomodate the opponents interests
    according to _is_better_bid with be_nice set to True
    """
    def _find_max_nice_bid(self, attempts) -> Bid:
        # some cheeky CPL currying
        return self._find_bid_with((lambda a, b: self._is_better_bid(a, b,  self.niceness, be_nice=True)), attempts)

    """
    Checks if bid a is better than bid b.
    If be_nice is True, will also consider the opponents utility according to opponent_model and
    is willing to sacrifice a niceness amount of utility when comparing in order to create a win-win
    """
    def _is_better_bid(self, a: Bid, b: Bid, niceness: Decimal, be_nice=False) -> bool:
        profile, _ = self._get_profile_and_progress()

        if not be_nice:
            return profile.getUtility(a) >= profile.getUtility(b)
        else:
            # TODO look into niceness possibly accumulating over multiple self.attempts
            # TODO Social welfare metric?
            return profile.getUtility(a) >= profile.getUtility(b) - niceness \
                and self.opponent_model.get_utility(a) >= self.opponent_model.get_utility(b)

    # ==============
    # === UTILS ====
    # ==============

    def _get_profile_and_progress(self) -> tuple[LinearAdditive, float]:
        profile: Profile = self._profileint.getProfile()
        progress: float = self._progress.get(0)

        return cast(LinearAdditive, profile), progress

    def _update_utilspace(self) -> None:  # throws IOException
        newutilspace = self._profileint.getProfile()
        if not newutilspace == self._utilspace:
            self._utilspace = cast(LinearAdditive, newutilspace)
            self._extendedspace = ExtendedUtilSpace(self._utilspace)

    # ===================
    # === DEBUG TOOLS ===
    # ===================

    def _print_utility(self, bid: Bid) -> None:
        profile, _ = self._get_profile_and_progress()
        print("Bid:", bid, "with utility:", profile.getUtility(bid))

    def _plot_characteristics(self) -> None:
        characteristics = {
            "thresholds": (list(range(len(self.thresholds))), self.thresholds)
        }
        print(characteristics)
        plot_characteristics(characteristics, len(self.thresholds))

