from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain

class FrequencyAnalyzzzer:
    def __init__(self, domain: Domain) -> None:
        self.number_bids: int = 0
        self.last_bid: Bid|None = None
        self.domain: Domain = domain

        self.frequency_table: dict[str, tuple[float, dict[Value, float], int]] = {}

    def _init_table(self) -> None:
        if self.last_bid is None:
            raise MissingHistoryException()

        issues = self.domain.getIssues()

        # init frequency table
        for issue in issues:
            values = self.domain.getValues(issue)
            value_freqs = { value : 0.0 for value in values }
            self.frequency_table[issue] = (1/len(issues), value_freqs, 0)

        issues_in_bid = self.last_bid.getIssues()

        # init with first bid
        for issue in issues_in_bid:
            freq, value_freqs, value_max_occurence = self.frequency_table[issue]

            freq: float = 1/len(issues_in_bid)
            issue_value: Value|None = self.last_bid.getValue(issue)

            if issue_value is None:
                raise ValueIsNoneException()

            value_freqs[issue_value] = 1.0
            value_max_occurence: int = 1

            self.frequency_table[issue] = (freq, value_freqs, value_max_occurence)


    def _update_issue_frequency(self, bid: Bid, issue: str, n) -> None:
        if self.last_bid is None:
            raise MissingHistoryException()

        issues = self.domain.getIssues()

        # if an issue has the same value
        if self.last_bid.getValue(issue) == bid.getValue(issue):
            # update frequency of current bid
            freq, value_freqs, value_max_occurence = self.frequency_table[issue]
            self.frequency_table[issue] = (freq + n, value_freqs, value_max_occurence)

            for other_issue in issues:
                # and 'compensate' this frequency change with others
                if not issue == other_issue:
                    other_freq, other_value_freqs, other_value_max_occurence = self.frequency_table[other_issue]
                    self.frequency_table[other_issue] = (other_freq - n/len(issues), other_value_freqs, other_value_max_occurence)

    def _update_issue_value_frequency(self, current_value: Value|None, issue: str) -> None:
        if current_value is None:
            raise ValueIsNoneException()

        freq, value_freqs, value_max_occurence = self.frequency_table[issue]
        current_freq = value_freqs[current_value]

        if current_freq == 1.0:
            max_repeat = 1
        else:
            max_repeat = 0

        for value in self.domain.getIssuesValues()[issue]:
            if value == current_value:
                occurence = 1
            else:
                occurence = 0

            value_freqs[value] = ((value_freqs[value] * value_max_occurence) + occurence) / (value_max_occurence + max_repeat)

        self.frequency_table[issue] = (freq, value_freqs, value_max_occurence + max_repeat)

    def add_bid(self, bid: Bid, n: float =.1) -> None:
        if bid is None:
            raise BidIsNoneException()

        self.number_bids += 1

        if self.last_bid is None:
            self.last_bid = bid
            self._init_table()
            return

        for issue in self.domain.getIssues():
            self._update_issue_frequency(bid, issue, n)
            self._update_issue_value_frequency(bid.getValue(issue), issue)

    def _get_max_value(self, issue: str) -> Value:
        _, value_frequencies, _ = self.frequency_table[issue]
        max_freq: float = -1.0
        max_key: Value|None = None

        for key, freq in value_frequencies.items():
            if max_freq < freq:
                max_freq = freq
                max_key = key

        assert max_key is not None

        return max_key

    def predict(self) -> Bid:
        if len(self.frequency_table) == 0:
            raise MissingHistoryException()

        prediction: dict[str, Value] = {}

        for issue in self.frequency_table:
            prediction[issue] = self._get_max_value(issue)

        return Bid(prediction)



class MissingHistoryException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class ValueIsNoneException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

class BidIsNoneException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)
