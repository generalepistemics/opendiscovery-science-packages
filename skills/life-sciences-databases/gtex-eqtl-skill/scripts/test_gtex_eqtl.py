from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import gtex_eqtl


def response(data: dict[str, object]) -> Mock:
    result = Mock()
    result.json.return_value = data
    result.raise_for_status.return_value = None
    return result


class FetchEqtlsTest(unittest.TestCase):
    @patch("gtex_eqtl.requests.Session")
    def test_uses_paging_metadata_for_limited_results(self, factory: Mock) -> None:
        session = factory.return_value
        session.get.return_value = response(
            {
                "data": [{"id": 1}, {"id": 2}],
                "paging_info": {
                    "numberOfPages": 3,
                    "page": 0,
                    "maxItemsPerPage": 2,
                    "totalNumberOfItems": 5,
                },
            }
        )

        rows, total, paging_info = gtex_eqtl.fetch_eqtls("variant", 2)

        self.assertEqual(rows, [{"id": 1}, {"id": 2}])
        self.assertEqual(total, 5)
        self.assertEqual(paging_info["totalNumberOfItems"], 5)
        session.get.assert_called_once()
        self.assertEqual(session.get.call_args.kwargs["params"]["itemsPerPage"], 2)
        self.assertEqual(session.get.call_args.kwargs["timeout"], gtex_eqtl.DEFAULT_TIMEOUT_S)
        self.assertEqual(
            session.get.call_args.kwargs["headers"],
            {"Accept": "application/json", "User-Agent": gtex_eqtl.USER_AGENT},
        )
        factory.assert_called_once_with()
        session.close.assert_called_once_with()

    @patch("gtex_eqtl.requests.Session")
    def test_fetches_every_page_when_no_limit_is_requested(self, factory: Mock) -> None:
        session = factory.return_value
        session.get.side_effect = [
            response(
                {
                    "data": [{"id": 1}, {"id": 2}],
                    "paging_info": {
                        "numberOfPages": 2,
                        "page": 0,
                        "maxItemsPerPage": 100_000,
                        "totalNumberOfItems": 3,
                    },
                }
            ),
            response(
                {
                    "data": [{"id": 3}],
                    "paging_info": {
                        "numberOfPages": 2,
                        "page": 1,
                        "maxItemsPerPage": 100_000,
                        "totalNumberOfItems": 3,
                    },
                }
            ),
        ]

        rows, total, _ = gtex_eqtl.fetch_eqtls("variant", None)

        self.assertEqual(rows, [{"id": 1}, {"id": 2}, {"id": 3}])
        self.assertEqual(total, 3)
        self.assertEqual(
            [call.kwargs["params"]["page"] for call in session.get.call_args_list],
            [0, 1],
        )
        self.assertEqual(
            [call.kwargs["params"]["itemsPerPage"] for call in session.get.call_args_list],
            [gtex_eqtl.GTEX_MAX_ITEMS_PER_PAGE, gtex_eqtl.GTEX_MAX_ITEMS_PER_PAGE],
        )
        factory.assert_called_once_with()
        session.close.assert_called_once_with()

    @patch("gtex_eqtl.requests.Session")
    def test_closes_shared_session_when_a_later_page_fails(self, factory: Mock) -> None:
        session = factory.return_value
        failure = gtex_eqtl.requests.HTTPError("GTEx page failed")
        failed_response = response({})
        failed_response.raise_for_status.side_effect = failure
        session.get.side_effect = [
            response(
                {
                    "data": [{"id": 1}],
                    "paging_info": {
                        "numberOfPages": 2,
                        "page": 0,
                        "totalNumberOfItems": 2,
                    },
                }
            ),
            failed_response,
        ]

        with self.assertRaisesRegex(gtex_eqtl.requests.HTTPError, "GTEx page failed"):
            gtex_eqtl.fetch_eqtls("variant", None)

        self.assertEqual(session.get.call_count, 2)
        factory.assert_called_once_with()
        session.close.assert_called_once_with()

    @patch("gtex_eqtl.requests.Session")
    def test_closes_session_when_response_is_not_json(self, factory: Mock) -> None:
        session = factory.return_value
        session.get.return_value.json.side_effect = ValueError("invalid JSON")

        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            gtex_eqtl.fetch_eqtls("variant", 1)

        factory.assert_called_once_with()
        session.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
