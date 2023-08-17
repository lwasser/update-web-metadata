import re
from datetime import datetime

import requests
from dataclasses import dataclass
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from typing import Any, Optional

from pyosmeta.contributors import ProcessContributors


def clean_date(a_date: Optional[str]) -> str:
    """Cleans up a datetime from github and returns a date string

    In some cases the string is manually entered month-day-year and in
    others it's a gh time stamp. finally sometimes it could be missing
    or text. handle all of those cases with this validator.
    """

    if a_date is None or a_date == "missing":
        return "missing"
    elif len(a_date) < 11:
        new_date = a_date.replace("/", "-").split("-")
        return f"{new_date[2]}-{new_date[0]}-{new_date[1]}"
    else:
        try:
            return (
                datetime.strptime(a_date, "%Y-%m-%dT%H:%M:%SZ")
                .date()
                .strftime("%Y-%m-%d")
            )
        except TypeError as t_error:
            print("Oops - missing data. Setting date to missing", t_error)
            return "missing"


class GhMeta(BaseModel):
    name: str
    description: str
    created_at: str
    stargazers_count: int
    watchers_count: int
    forks: int
    open_issues_count: int
    forks_count: int
    documentation: Optional[str]  # Jointly is missing documentation
    contrib_count: int
    last_commit: str

    @field_validator(
        "last_commit",
        "created_at",
        mode="before",
    )
    @classmethod
    def clean_date(cls, a_date: Optional[str]) -> str:
        """Cleans up a datetime from github and returns a date string

        Runs the general clean_date function in this module as a validator.
        """

        return clean_date(a_date)


class ReviewModel(BaseModel):
    # Make sure model populates both aliases and original attr name
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    package_name: Optional[str] = ""
    package_description: str = Field(
        "", validation_alias=AliasChoices("one-line_description_of_package")
    )
    submitting_author: dict[str, Optional[str]] = {}
    all_current_maintainers: list[dict[str, str | None]] = {}
    repository_link: Optional[str] = None
    version_submitted: Optional[str] = None
    categories: Optional[list[str]] = None
    editor: dict[str, str | None] = {}
    reviewer_1: dict[str, str | None] = {}
    reviewer_2: dict[str, str | None] = {}
    archive: Optional[str] = None
    version_accepted: Optional[str] = None
    date_accepted: Optional[str] = None
    created_at: str = None
    updated_at: str = None
    closed_at: Optional[str] = None
    issue_link: str = None
    gh_meta: GhMeta

    @field_validator(
        "date_accepted",
        "created_at",
        "updated_at",
        "closed_at",
        mode="before",
    )
    @classmethod
    def clean_date(cls, a_date: Optional[str]) -> str:
        """Cleans up a datetime from github and returns a date string

        Runs the general clean_date function in this module as a validator.

        """

        return clean_date(a_date)


@dataclass
class ProcessIssues:
    """
    A class that processes GitHub issues in our peer review process and returns
    metadata about each package.


    """

    def __init__(self, org, repo_name, label_name):
        """
        More here...

        Parameters
        ----------
        org : str
            Organization name where the issues exist
        repo_name : str
            Repo name where the software review issues live
        label_name : str
            Label of issues to grab - e.g. pyos approved
        GITHUB_TOKEN : str
            API token needed to authenticate with GitHub
            Inherited from super() class
        """
        self.org: str = org
        self.repo_name: str = repo_name
        self.label_name: str = label_name
        self.contrib_instance = ProcessContributors([])

        self.GITHUB_TOKEN = self.contrib_instance.get_token()

    gh_stats = [
        "name",
        "description",
        "homepage",
        "created_at",
        "stargazers_count",
        "watchers_count",
        "forks",
        "open_issues_count",
        "forks_count",
    ]

    @property
    def api_endpoint(self):
        url = (
            f"https://api.github.com/repos/{self.org}/{self.repo_name}/"
            f"issues?labels={self.label_name}&state=all"
        )
        return url

    # Set up the API endpoint
    def _get_response(self):
        """
        # Make a GET request to the API endpoint
        """

        print(self.api_endpoint)

        try:
            response = requests.get(
                self.api_endpoint,
                headers={"Authorization": f"token {self.GITHUB_TOKEN}"},
            )
            response.raise_for_status()

        except requests.HTTPError as exception:
            raise exception

        return response

    def return_response(self) -> list[dict[str, object]]:
        """
        Deserialize json response to list of dicts.

        Parameters
        ----------
        username : str
            GitHub username of person authenticating to hit the GitHub API

        Returns
        -------
        list
            List of dict items each containing a review issue
        """
        response = self._get_response()
        return response.json()

    def _contains_keyword(self, string: str) -> bool:
        """
        Returns true if starts with any of the 3 items below.
        """
        return string.startswith(
            ("Submitting", "Editor", "Reviewer", "All current maintainers")
        )

    def _clean_name(self, a_str: str) -> str:
        """Helper to strip unwanted chars from text"""

        unwanted = ["(", ")", "@"]
        for char in unwanted:
            a_str = a_str.replace(char, "")

        return a_str.strip()

    def _get_line_meta(self, line_item: list[str]) -> dict[str, object]:
        """
        Parameters
        ----------
        line_item : list
            A single list item representing a single line in the issue
            containing metadata for the review.
            This comment is metadata for the review that the author fills out.

        Returns
        -------
            Dict containing the metadata for a submitting author, reviewer or
            maintainer(s)
        """

        meta = {}
        a_key = line_item[0].lower().replace(" ", "_")
        if self._contains_keyword(line_item[0]):
            if line_item[0].startswith("All current maintainers"):
                names = line_item[1].split(",")
                # There are at least 2 maintainers if there is a comma
                # if len(names) > 1:
                meta[a_key] = []
                for aname in names:
                    # Add each maintainer to the dict
                    user = aname.split("@")
                    # Clean
                    user = [self._clean_name(a_str) for a_str in user]
                    a_maint = {
                        "name": self._clean_name(user[0]),
                        "github_username": self._clean_name(user[1]),
                    }
                    # filtered_list = list(filter(None, my_list))
                    meta[a_key].append(a_maint)
            else:
                names = line_item[1].split("(", 1)
                if len(names) > 1:
                    meta[a_key] = {
                        "github_username": self._clean_name(names[1]),
                        "name": self._clean_name(names[0]),
                    }
                else:
                    meta[a_key] = {
                        "github_username": self._clean_name(names[0]),
                        "name": "",
                    }
        elif len(line_item) > 1:
            meta[a_key] = line_item[1].strip()
        else:
            meta[a_key] = self._clean_name(line_item[0])
        return meta

    def parse_issue_header(
        self, issues: list[str], total_lines: int = 15
    ) -> dict[str, str]:
        """
        A function that parses through the header of an issue.
        It returns

        Parameters
        ----------
        issues : list
            List returned from the return_response method that contains the
            metadata at the top of each issue
        total_lines : int
            an integer representing the total number of lines to parse in the
            issue header. Default = 15

        Returns
        -------
        Dict
            A dictionary containing metadata for the issue including the
            package name, description, review team, version submitted etc.
            See key_order below for the full list of keys.
        """

        meta_dates = ["created_at", "updated_at", "closed_at"]

        review = {}
        for issue in issues:
            package_name, body_data = self.parse_comment(issue)
            if not package_name:
                continue
            # Index of 15 should include date accepted in the review meta
            review[package_name] = self.get_issue_meta(body_data, total_lines)
            # Add issue open and close date to package meta
            # Created, opened & closed dates are in GitHub Issue response
            for a_date in meta_dates:
                # TODO: this could become a validator
                review[package_name][a_date] = issue[
                    a_date
                ]  # self._clean_date(issue[a_date])
            # Get categories and issue review link
            review[package_name]["categories"] = self.get_categories(body_data)
            review[package_name]["issue_link"] = issue["url"].replace(
                "https://api.github.com/repos/", "https://github.com/"
            )

            review_clean = {
                key: value
                for key, value in review[package_name].items()
                if not key.startswith("##")
                and not key.startswith("---")
                and not key.startswith("-_[x]_i_agree")
            }
            review[package_name] = review_clean
            # filtered = {}
            # for key, value in review.items():
            #     print(key)
            #     if not key.startswith("##") and not key.startswith("-"):
            #         filtered[key] = value

            # # Clean markdown url's from editor, and reviewer lines
            # TODO - this could be a reviewer name cleanup validaotr
            # types = ["editor", "reviewer_1", "reviewer_2"]
            # user_values = ["github_username", "name"]
            # for a_type in types:
            #     for user_value in user_values:
            #         issue_meta[a_type][user_value] = (
            #             issue_meta[a_type][user_value]
            #             .replace("https://github.com/", "")
            #             .replace("[", "")
            #             .replace("]", "")
            #         )

            # review[package_name] = issue_meta

        return review

    def get_issue_meta(
        self,
        body_data: list[str],
        end_range: int,
    ) -> dict[str, str]:
        """
        Parse through the top of an issue and grab the metadata for the review.

        Parameters
        ----------
        body_data : list
            A list containing all body data for the top comment in an issue.
        end_range : int
            The number of lines to parse at the top of the issue (this may
            change over time so this variable allows us to have different
            processing based upon the date of the issue being opened)

        Returns
        -------
            dict
        """
        issue_meta = {}
        for item in body_data[0:end_range]:
            # Clean date accepted element
            if "Date accepted".lower() in item[0].lower():
                item[0] = "Date accepted"
            issue_meta.update(self._get_line_meta(item))

        return issue_meta

    def get_repo_endpoints(
        self, review_issues: dict[str, str]
    ) -> dict[str, str]:
        """
        Returns a list of repository endpoints

        Parameters
        ----------
        review_issues : dict
            Dictionary containing all of the review issue paths.

        Returns
        -------
            Dict
                Containing package_name: endpoint for each review.

        """

        all_repos = {}
        for a_package in review_issues.keys():
            repo = review_issues[a_package]["repository_link"].strip("/")
            owner, repo = repo.split("/")[-2:]
            # TODO: could be simpler code - Remove any link remnants
            pattern = r"[\(\)\[\]?]"
            owner = re.sub(pattern, "", owner)
            repo = re.sub(pattern, "", repo)
            all_repos[
                a_package
            ] = f"https://api.github.com/repos/{owner}/{repo}"
        return all_repos

    def parse_comment(self, issue: dict[str, str]) -> tuple[str, list[str]]:
        """
        Parses an issue comment for pyOpenSci review. Returns the package name
        and the body of the comment parsed into a list of elements.

        Parameters
        ----------
        issue : dict
            A dictionary containing the json response for an issue comment.


        Returns
        -------
            package_name : str
                The name of the package
            comment : list
                A list containing the comment elements in order
        """

        body = issue["body"]
        # Clean line breaks (could be done with a regex too)
        lines = body.split("\n")
        lines = [a_line.strip("\r").strip() for a_line in lines]
        # Some users decide to hold the issue titles.
        # For those, clean the markdown bold ** element
        lines = [
            line.replace("**", "").strip()
            for line in lines
            if line.strip() != ""
        ]
        # You need a space after : or else it will break https:// in two
        body_data = [line.split(": ") for line in lines if line.strip() != ""]

        # Loop through issue header and grab relevant review metadata
        name_index = next(
            (
                i
                for i, sublist in enumerate(body_data)
                if sublist[0] == "Package Name"
            ),
            None,
        )

        package_name = body_data[name_index][1] if name_index else None

        return package_name, body_data

    def get_gh_metrics(
        self,
        endpoints: dict[str, str],
        reviews: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """
        Get GitHub metrics for each review based on provided endpoints.

        Parameters:
        ----------
        endpoints : dict
            A dictionary mapping package names to their GitHub URLs.
        reviews : dict
            A dictionary containing review data.

        Returns:
        -------
        dict
            Updated review data with GitHub metrics.
        """
        pkg_meta = {}
        for pkg_name, url in endpoints.items():
            print("Getting GitHub stats for", pkg_name)
            pkg_meta[pkg_name] = self.get_repo_meta(url, self.gh_stats)

            pkg_meta[pkg_name]["contrib_count"] = self.get_repo_contribs(url)
            pkg_meta[pkg_name]["last_commit"] = self.get_last_commit(url)
            # Add github meta to review metadata
            reviews[pkg_name]["gh_meta"] = pkg_meta[pkg_name]

        return reviews

    def get_repo_meta(self, url: str, stats_list: list) -> dict:
        """
        Returns a set of GH stats from each repo of our reviewed packages.

        """
        stats_dict = {}
        # Get the url (normally the docs) and description of a repo!
        response = requests.get(
            url, headers={"Authorization": f"token {self.GITHUB_TOKEN}"}
        )

        # TODO: should this be some sort of try/except how do i catch these
        # Response errors in the best way possible?
        if response.status_code == 404:
            print("Can't find: ", url, ". Did the repo url change?")
        elif response.status_code == 403:
            print("Oops you may have hit an API limit. Exiting")
            print(f"API Response Text: {response.text}")
            print(f"API Response Headers: {response.headers}")
            exit()

        # Extract the description and homepage URL from the response JSON
        else:
            data = response.json()
            for astat in stats_list:
                stats_dict[astat] = data[astat]
            stats_dict["documentation"] = stats_dict.pop("homepage")
            # stats_dict["created_at"] = self._clean_date(
            #     stats_dict["created_at"]
            # )

        return stats_dict

    def get_repo_contribs(self, url: str) -> dict:
        """
        Returns a list of contributors to a specific repo.

        """
        repo_contribs = url + "/contributors"
        # Small script to get the url (normally the docs) and repo description
        response = requests.get(
            repo_contribs,
            headers={"Authorization": f"token {self.GITHUB_TOKEN}"},
        )

        if response.status_code == 404:
            print("Can't find: ", repo_contribs, ". Did the repo url change?")
        # Extract the description and homepage URL from the JSON response
        else:
            return len(response.json())

    def get_last_commit(self, repo: str) -> str:
        """Returns the last commit to the repository.

        Parameters
        ----------
        str : string
            A string containing a datetime object representing the datetime of
            the last commit to the repo
        """
        url = repo + "/commits"
        response = requests.get(
            url, headers={"Authorization": f"token {self.GITHUB_TOKEN}"}
        ).json()
        date = response[0]["commit"]["author"]["date"]

        return date

    def get_categories(
        self, issue_body_list: list[list[str]], fmt: bool = True
    ) -> list[str]:
        """Parse through a pyOS review issue and grab categories associated
        with a package

        Parameters
        ----------
        issue_body_list : list[list[str]]
            The first comment from the issue split into lines and then the
            lines split as by self.parse_comment()

        fmt : bool
            Applies some formatting changes to the categories to match what is
            required for the website.
        """
        # Find the starting index of the category section
        start_index = None
        for i in range(len(issue_body_list)):
            if issue_body_list[i][0].startswith("- Please indicate which"):
                start_index = i + 1
                break
        # NOTE - some issues have line after that startswith "Check out our"
        # For those issues advance i += 1
        if issue_body_list[start_index][0].startswith("Check out our"):
            start_index += 1

        if start_index is None:
            # If we couldn't find the starting index, return an empty list
            return []

        # Iterate through lines and grab the relevant text
        cat_matches = ["[x]", "[X]"]
        categories: list[str] = []
        for i in range(start_index, len(issue_body_list)):  # 30):
            line = issue_body_list[i][0].strip()
            checked = any([x in line for x in cat_matches])

            if line.startswith("- [") and checked:
                category = line[line.index("]") + 2]
                categories.append(category)
            elif not line.startswith("- ["):
                break

        if fmt:
            categories = [c.lower().replace(" ", "-") for c in categories]
        return categories
