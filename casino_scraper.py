import re
import time

import pandas
from selenium import webdriver
from selenium.common import NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

from linkedin_helper import set_up_linkedin_driver, CasinoCompanySearch, get_linkedin_company_link


class CasinoScraper:
    def __init__(self):
        self.ask_gamblers_casinos_dict = {}
        self.casinos_dict = {}
        self.linkedin_driver = None
        self.email_regex = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')
        self.number_regex = re.compile(r'\+\d{5,}|\+\d*\(\d{1,}\)\d{5,}|\+\d*\s*\(\d{2,}\)\s*\d{5,}')

    def get_top_ten_casinos_from_ask_gamblers(self, headless_mode):
        options = Options()
        options.page_load_strategy = 'eager'
        if headless_mode:
            options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
        driver.get("https://www.askgamblers.com/online-casinos")

        casinos = driver.find_elements(By.CSS_SELECTOR, ".top-10-card>a")
        for casino in casinos:
            casino_name = casino.get_attribute("title")
            self.casinos_dict[casino_name] = {}
            self.ask_gamblers_casinos_dict[casino_name] = {'review_links': casino.get_attribute("href")}
        driver.quit()

    def get_extra_casion_info_from_askgamblers_review(self, target_url, current_casino, headless_mode):
        options = Options()
        if headless_mode:
            options.add_argument("--headless=new")
        options.page_load_strategy = 'eager'
        current_driver = webdriver.Chrome(options=options)
        current_driver.get(target_url)
        element_with_link = current_driver.find_element(By.CSS_SELECTOR, ".review-details__item")
        raw_text = element_with_link.text.split("://")[1]
        self.casinos_dict[current_casino]['website'] = "http://" + raw_text
        link_elements = current_driver.find_elements(By.CSS_SELECTOR, ".tab-slider-trigger")
        for link_element in link_elements:
            if link_element.text == "Customer Support":
                link_element.click()
                support_elems = current_driver.find_elements(By.CSS_SELECTOR, "div.review-details__text")
                for elem in support_elems:
                    if elem.text:
                        h = re.search(self.email_regex, elem.text)
                        if h:
                            support_email = h.group(0)
                            self.casinos_dict[current_casino]['email'] = support_email
                        number_match = re.search(self.number_regex, elem.text)
                        if number_match:
                            support_number = number_match.group(0)
                            self.casinos_dict[current_casino]['number'] = support_number

        current_driver.quit()

    @staticmethod
    def try_elem_with_diff_names(current_driver, link_name):
        contact_us = None
        try:
            contact_us = current_driver.find_element(By.LINK_TEXT, link_name)
        except NoSuchElementException:
            try:
                contact_us = current_driver.find_element(By.PARTIAL_LINK_TEXT, link_name)
            except NoSuchElementException:
                pass
        return contact_us

    def find_contacts_button(self, current_driver):
        """
        Find the contact us button since the spellings can be different on each site
        """
        contact_btn = self.try_elem_with_diff_names(current_driver, "Contact Us")
        if contact_btn: return contact_btn
        contact_btn_2 = self.try_elem_with_diff_names(current_driver, "Contact us")
        if contact_btn_2: return contact_btn_2
        contact_btn_3 = self.try_elem_with_diff_names(current_driver, "Contacts")
        if contact_btn_3: return contact_btn_3
        contact_btn_4 = self.try_elem_with_diff_names(current_driver, "Contact")
        if contact_btn_4: return contact_btn_4
        return None

    def visit_individual_site(self, casino_name, casino_site, headless_mode):
        """
        Crawl the actual websites of the casino to get more details.
        :param casino_name: Name of casino
        :param casino_site: Website url of casino
        :param headless_mode: Determine if the browser would run in headless mode
        """
        try:
            self.casinos_dict[casino_name]
        except KeyError:
            self.casinos_dict[casino_name] = {}
        options = Options()
        options.browser_version = "113"
        options.page_load_strategy = 'eager'
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("test-type")
        if headless_mode:
            options.add_argument("--headless=new")

        current_driver = webdriver.Chrome(options=options)
        current_driver.get(casino_site)
        current_driver.implicitly_wait(30)

        # search for skype links and telegram
        ignored_exceptions = (NoSuchElementException, StaleElementReferenceException,)
        _ = WebDriverWait(current_driver, 30, ignored_exceptions=ignored_exceptions) \
            .until(expected_conditions.presence_of_all_elements_located((By.TAG_NAME, "a")))
        a_links = current_driver.find_elements(By.TAG_NAME, "a")[-7:]

        for link in a_links:
            link_href = link.get_attribute("href")
            if link_href is None:
                continue
            if "skype.com" in link_href:
                self.casinos_dict[casino_name]["skype"] = link_href
            if "t.me" in link_href:
                self.casinos_dict[casino_name]["telegram"] = link_href
            time.sleep(10)

        contact_us = self.find_contacts_button(current_driver)
        if contact_us:
            try:
                contact_us.click()
            except ElementClickInterceptedException:
                current_driver.execute_script("arguments[0].click();", contact_us)
        time.sleep(2)

        # only get number, if not previously gotten
        try:
            self.casinos_dict[casino_name]['number']
        except KeyError:
            number_match = re.search(self.number_regex, current_driver.page_source)
            if number_match:
                support_number = number_match.group(0)
                self.casinos_dict[casino_name]['number'] = support_number
        current_driver.quit()

    def parse_from_linkedin(self, casino_name, casino_url, headless_mode=False):
        """
        Gets the employees of a casino from linkedin.
        Employees are gotten from the company's linkedin profile, which is gotten by
        searching via a search engine.
        :param casino_name: The name of  the casino
        :param casino_url: Url of casino website, helps with the search for the linkedin url
        :param headless_mode: Determine if the browsers open in headless mode
        """
        # use the same driver for linkedIn, to prevent multiple logins on linkedin
        if self.linkedin_driver is None:
            self.linkedin_driver = set_up_linkedin_driver(headless_mode)

        linkedin_casino_profile = get_linkedin_company_link(casino_url, headless_mode)
        if linkedin_casino_profile is None:
            return
        try:
            company = CasinoCompanySearch(linkedin_casino_profile, driver=self.linkedin_driver,
                                          get_employees=True, close_on_complete=False)
        except Exception as e:
            print("Exception gotten was")
            print(e)
            return
        company_json = company.to_json()
        # dont attach if company is not a casino
        if company_json['industry'] == "Gambling Facilities and Casinos":
            del company_json['industry']
            self.casinos_dict[casino_name]['linkedin'] = company_json

    def get_casinos(self, headless_mode):
        """
        Gets the casino names from different aggregate sites.
        Currently, only ask gamblers is supported
        :param headless_mode: Determines if the browser should be ran in headless mode
        """
        self.get_top_ten_casinos_from_ask_gamblers(headless_mode)
        for casino_name in self.ask_gamblers_casinos_dict:
            self.get_extra_casion_info_from_askgamblers_review(self.ask_gamblers_casinos_dict[casino_name]['review_links'],
                                                               casino_name, headless_mode)

    def run(self, headless_mode=False):
        """
        The main function that scrapes the gambling sites and saves the data
        :param headless_mode: Determines if the browser should be ran in headless mode
        """
        self.get_casinos(headless_mode)  # populate the casinos_dict

        for casino_name in self.casinos_dict:
            self.visit_individual_site(casino_name, self.casinos_dict[casino_name]['website'], headless_mode)
        for casino_name in self.casinos_dict:
            self.parse_from_linkedin(casino_name, self.casinos_dict[casino_name]['website'], headless_mode)
            time.sleep(10)

        df = pandas.DataFrame.from_dict(self.casinos_dict)
        df.to_excel('data.xlsx')


if __name__ == "__main__":

    CasinoScraper().run()
