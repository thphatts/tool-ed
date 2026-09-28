import unittest

from ai_reasoner import AIContextReasoner


class ChoiceParsingTests(unittest.TestCase):
    def setUp(self):
        self.reasoner = AIContextReasoner.__new__(AIContextReasoner)

    def test_choice_text_wins_over_conflicting_index(self):
        options = ["send messages.", "watch television.", "play music."]
        data = {"best_option_index": 0, "best_option_text": "play music."}
        self.assertEqual(self.reasoner._parse_choice(data, options), 2)

    def test_invalid_model_response_is_not_option_zero(self):
        self.assertIsNone(self.reasoner._parse_choice({"best_option_index": "unknown"}, ["a", "b"]))
        self.assertIsNone(self.reasoner._local_semantic_match("", ["a", "b"], ""))

    def test_local_match_requires_evidence(self):
        options = ["send messages.", "watch television.", "play music."]
        self.assertEqual(
            self.reasoner._local_semantic_match(
                "A gramophone is used to...", options,
                "A gramophone is an old machine used to play music."
            ),
            2,
        )

    def test_negative_question_picks_least_supported_option(self):
        options = ["the car was repaired", "pick up the dress", "win the lottery"]
        self.assertEqual(
            self.reasoner._local_semantic_match(
                "Which is not true?", options,
                "Lori asked Marcy to pick up the dress. The car was repaired."
            ),
            2,
        )

    def test_true_false_uses_transcript_context(self):
        self.assertEqual(
            self.reasoner._local_semantic_match(
                "Lori is calling from the garage.", ["True", "False"],
                "Lori called from the garage while her car was being fixed."
            ),
            0,
        )

    def test_mapping_does_not_invent_word(self):
        self.assertEqual(
            self.reasoner._validate_mapping({"0": "not in bank"}, ["known answer"], 1),
            {},
        )

    def test_mapping_normalizes_zero_based_slots(self):
        self.assertEqual(
            self.reasoner._validate_mapping(
                {"0": "first", "1": "second"}, ["first", "second"], 2
            ),
            {"1": "first", "2": "second"},
        )


if __name__ == "__main__":
    unittest.main()
