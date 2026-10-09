import unittest
from unittest.mock import MagicMock, patch

from buyin_session_bootstrap import bootstrap_buyin_page, is_buyin_domain_url, is_buyin_square_url, is_similar_mode_url


class BuyinSessionBootstrapTest(unittest.TestCase):
    def test_navigation_with_failed_content_is_not_ready(self):
        from buyin_session_bootstrap import buyin_page_ready
        page = MagicMock()
        page.is_closed.return_value = False
        page.url = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
        page.locator.return_value.count.return_value = 0
        page.locator.return_value.inner_text.return_value = "达人广场 找达人 加载失败，请稍后重试"
        self.assertFalse(buyin_page_ready(page))
        page.locator.return_value.count.return_value = 1
        page.locator.return_value.nth.return_value.get_attribute.return_value = "搜索达人昵称或抖音号"
        self.assertTrue(buyin_page_ready(page))

    def test_embedded_redirect_bootstraps_same_shop_without_borrowing_sibling(self):
        page = MagicMock()
        page.is_closed.return_value = False
        page.url = "https://www.douyinec.com/"
        context = MagicMock()
        with patch("buyin_session_bootstrap.buyin_page_ready", return_value=False), \
             patch("buyin_session_bootstrap.wait_for_page_ready", return_value=False), \
             patch("buyin_session_bootstrap.bootstrap_embedded_alliance") as enter:
            self.assertIs(bootstrap_buyin_page(context, preferred_page=page), page)
        enter.assert_called_once_with(page)
        context.new_page.assert_not_called()

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
