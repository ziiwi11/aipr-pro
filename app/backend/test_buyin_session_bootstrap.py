import unittest

from buyin_session_bootstrap import is_buyin_domain_url, is_buyin_square_url, is_similar_mode_url


class BuyinSessionBootstrapTest(unittest.TestCase):
    def test_recognizes_real_buyin_square_and_rejects_public_redirect(self):
        self.assertTrue(is_buyin_square_url(
            "https://buyin.jinritemai.com/dashboard/servicehall/daren-square?dareSquareType=FindSimilarDaren"
        ))
        self.assertFalse(is_buyin_square_url("https://www.douyinec.com/"))

    def test_distinguishes_similar_creator_mode_from_regular_square(self):
        self.assertTrue(is_similar_mode_url(
            "https://buyin.jinritemai.com/dashboard/servicehall/daren-square?dareSquareType=FindSimilarDaren"
        ))
        self.assertFalse(is_similar_mode_url(
            "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
        ))

    def test_recognizes_other_logged_in_buyin_pages_for_direct_square_navigation(self):
        self.assertTrue(is_buyin_domain_url(
            "https://buyin.jinritemai.com/dashboard/servicehall/clue-daren"
        ))
        self.assertFalse(is_buyin_domain_url("https://www.douyinec.com/"))


if __name__ == "__main__":
    unittest.main()
