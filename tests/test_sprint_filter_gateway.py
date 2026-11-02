import unittest
from unittest.mock import MagicMock

from extensions.twoa_programme.delivery_health import FilterSprintGateway


class FilterSprintGatewayTests(unittest.TestCase):
    def test_reads_sprint_metadata_from_filter_and_serves_state_pages(self):
        http = MagicMock()
        http.post_json.return_value = {
            "issues": [
                {
                    "fields": {
                        "customfield_10020": [
                            {"id": 42, "name": "Kakariki Sprint 42", "state": "closed", "startDate": "2026-04-01", "endDate": "2026-04-15"},
                            {"id": 43, "name": "Kakariki Sprint 43", "state": "active", "startDate": "2026-04-16"},
                        ]
                    }
                },
                {
                    "fields": {
                        "customfield_10020": [
                            {"id": 42, "name": "Kakariki Sprint 42", "state": "closed", "startDate": "2026-04-01", "endDate": "2026-04-15"},
                            {"id": 44, "name": "Kakariki Sprint 44", "state": "closed", "startDate": "2026-04-16", "endDate": "2026-04-30"},
                        ]
                    }
                },
            ],
            "isLast": True,
        }
        gateway = FilterSprintGateway(http, {893: 10728})

        first_page = gateway.get_json(
            "rest/agile/1.0/board/893/sprint",
            params={"state": "closed", "startAt": 0, "maxResults": 1},
        )
        second_page = gateway.get_json(
            "rest/agile/1.0/board/893/sprint",
            params={"state": "closed", "startAt": 1, "maxResults": 1},
        )
        active = gateway.get_json(
            "rest/agile/1.0/board/893/sprint",
            params={"state": "active", "startAt": 0, "maxResults": 50},
        )

        self.assertEqual([sprint["id"] for sprint in first_page["values"]], [42])
        self.assertFalse(first_page["isLast"])
        self.assertEqual([sprint["id"] for sprint in second_page["values"]], [44])
        self.assertTrue(second_page["isLast"])
        self.assertEqual([sprint["id"] for sprint in active["values"]], [43])
        http.post_json.assert_called_once_with(
            "/rest/api/3/search/jql",
            body={
                "jql": "filter = 10728",
                "maxResults": 100,
                "fields": ["customfield_10020"],
            },
        )

    def test_unmapped_board_uses_regular_agile_endpoint(self):
        http = MagicMock()
        http.get_json.return_value = {"values": [], "isLast": True}
        gateway = FilterSprintGateway(http, {893: 10728})

        response = gateway.get_json(
            "rest/agile/1.0/board/1725/sprint",
            params={"state": "closed", "startAt": 0, "maxResults": 50},
        )

        self.assertEqual(response, {"values": [], "isLast": True})
        http.get_json.assert_called_once_with(
            "/rest/agile/1.0/board/1725/sprint",
            params={"state": "closed", "startAt": 0, "maxResults": 50},
        )
        http.post_json.assert_not_called()

    def test_kikorangi_board_uses_filter_10729(self):
        http = MagicMock()
        http.post_json.return_value = {
            "issues": [
                {
                    "fields": {
                        "customfield_10020": [
                            {"id": 52, "name": "Kikorangi Sprint 52", "state": "closed", "startDate": "2026-04-01", "endDate": "2026-04-15"}
                        ]
                    }
                }
            ],
            "isLast": True,
        }
        gateway = FilterSprintGateway(http, {893: 10728, 992: 10729})

        response = gateway.get_json(
            "rest/agile/1.0/board/992/sprint",
            params={"state": "closed", "startAt": 0, "maxResults": 50},
        )

        self.assertEqual([sprint["id"] for sprint in response["values"]], [52])
        http.post_json.assert_called_once_with(
            "/rest/api/3/search/jql",
            body={
                "jql": "filter = 10729",
                "maxResults": 100,
                "fields": ["customfield_10020"],
            },
        )


if __name__ == "__main__":
    unittest.main()