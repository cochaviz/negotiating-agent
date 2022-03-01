import logging
from random import randint
from typing import cast

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
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
from utils.frequency_analyzer import FrequencyAnalyzer, MissingHistoryException


class CustomAgent(DefaultParty):
    """
    Template agent that offers random bids until a bid with sufficient utility is offered.
    """

    def __init__(self):
        super().__init__()
        self.getReporter().log(logging.INFO, "party is initialized")
        self._profile: ProfileInterface
        self._last_received_bid: Bid

        # General settings
        self.opponent_model = FrequencyAnalyzer()
        self.reservation_value: float = .8

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
            self._profile = ProfileConnectionFactory.create(
                info.getProfile().getURI(), self.getReporter()
            )
            self.opponent_model.set_domain(self._profile.getProfile().getDomain())
        # ActionDone is an action send by an opponent (an offer or an accept)
        elif isinstance(info, ActionDone):
            action: Action = cast(ActionDone, info).getAction()

            # if it is an offer, set the last received bid
            if isinstance(action, Offer):
                self._last_received_bid = cast(Offer, action).getBid()
        # YourTurn notifies you that it is your turn to act
        elif isinstance(info, YourTurn):
            # execute a turn
            self._myTurn()

            # log that we advanced a turn
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
        super().terminate()
        if self._profile is not None:
            self._profile.close()
            self._profile = None

    #######################################################################################
    ########## THE METHODS BELOW THIS COMMENT ARE OF MAIN INTEREST TO THE COURSE ##########
    #######################################################################################

    # give a description of your agent
    def getDescription(self) -> str:
        return "Template agent for Collaborative AI course"

    # execute a turn
    def _myTurn(self):
        self.opponent_model.add_bid(self._last_received_bid)

        try:
            predicted_bid = self.opponent_model.predict()
            print("Most likely next bid:", predicted_bid)
        except MissingHistoryException:
            print("Missing history, need more bids")

        # check if the last received offer if the opponent is good enough
        if self._is_acceptable(self._last_received_bid):
            # if so, accept the offer
            action = Accept(self._me, self._last_received_bid)
        else:
            # if not, find a bid to propose as counter offer
            bid = self._find_bid()
            action = Offer(self._me, bid)

        # send the action
        self.getConnection().send(action)

    def _getProfileAndProgress(self) -> tuple[Profile, float]:
        profile: Profile = self._profile.getProfile()
        progress: float = self._progress.get(0)

        return profile, progress

    # method that checks if we should agree with an incoming offer
    def _is_acceptable(self, bid: Bid) -> bool:
        if bid is None:
            return False

        profile, progress = self._getProfileAndProgress()

        # Has to be at least more than the reservation value
        return profile.getUtility(bid) > self.reservation_value and progress > 0.8

    # method that checks if we should agree with an outgoing offer
    def _isGoodOutgoing(self, bid: Bid) -> bool:
        if bid is None:
            return False

        profile, progress = self._getProfileAndProgress()

        return profile.getUtility(bid) > self.reservation_value and progress > 0.8

    def _find_bid(self, attempts=50) -> Bid:
        # compose a list of all possible bids
        domain = self._profile.getProfile().getDomain()
        all_bids = AllBidsList(domain)
        _, progress = self._getProfileAndProgress()

        if progress < 0.1:
            return self._find_max_bid(attempts)

        # take 50 attempts at finding a random bid that is acceptable to us
        for _ in range(attempts):
            bid = all_bids.get(randint(0, all_bids.size() - 1))
            if self._isGoodOutgoing(bid):
                break

        return bid

    def _find_max_bid(self, attempts=50) -> Bid:
        # compose a list of all possible bids
        profile, _ = self._getProfileAndProgress()
        domain = profile.getDomain()
        all_bids = AllBidsList(domain)


        # take 50 attempts at finding a random bid that is acceptable to us
        maxBid = all_bids.get(0)

        for _ in range(attempts):
            bid = all_bids.get(randint(1, all_bids.size() - 1))
            maxBid = maxBid if (profile.getUtility(maxBid) > profile.getUtility(bid)) else bid

        return maxBid
