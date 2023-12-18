import os
import re
import time

from dotenv import load_dotenv
from linkedin_scraper import actions, Company
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.chrome.options import Options

load_dotenv()

AD_BANNER_CLASSNAME = ('ad-banner-container', '__ad')

def set_up_linkedin_driver(headless_mode=False):
    if headless_mode:
        options = Options()
        options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
    else:
        driver = webdriver.Chrome()

    # linkedin Credentials
    email = os.environ["LINKEDIN_EMAIL"]
    password = os.environ["LINKEDIN_PASSWORD"]
    actions.login(driver, email, password) # login via the driver
    return driver


class CasinoCompanySearch(Company):
    def to_json(self):
        custom_employees = []
        for employee in self.employees:
            if employee:
                employee['profile_url'] = employee.pop('linkedin_url')
                custom_employees.append(employee)
        return {
            "industry":self.industry,
            'name':self.name,
            "employees": custom_employees
        }


    def scrape_logged_in(self, get_employees = True, close_on_complete = True):
        driver = self.driver

        driver.get(self.linkedin_url)

        _ = WebDriverWait(driver, 3).until(EC.presence_of_all_elements_located((By.XPATH, '//span[@dir="ltr"]')))

        navigation = driver.find_element(By.CLASS_NAME, "org-page-navigation__items ")

        self.name = driver.find_element(By.XPATH,'//span[@dir="ltr"]').text.strip()

        # Click About Tab or View All Link
        try:
          self.__find_first_available_element__(
            navigation.find_elements(By.XPATH, "//a[@data-control-name='page_member_main_nav_about_tab']"),
            navigation.find_elements(By.XPATH, "//a[@data-control-name='org_about_module_see_all_view_link']"),
          ).click()
        except:
          driver.get(os.path.join(self.linkedin_url, "about"))

        _ = WebDriverWait(driver, 3).until(EC.presence_of_all_elements_located((By.TAG_NAME, 'section')))
        time.sleep(3)

        if 'Cookie Policy' in driver.find_elements(By.TAG_NAME, "section")[1].text or any(classname in driver.find_elements(By.TAG_NAME, "section")[1].get_attribute('class') for classname in AD_BANNER_CLASSNAME):
            section_id = 4
        else:
            section_id = 3
       #section ID is no longer needed, we are using class name now.
        grid = driver.find_element(By.CLASS_NAME, "artdeco-card.org-page-details-module__card-spacing.artdeco-card.org-about-module__margin-bottom")
        descWrapper = grid.find_elements(By.TAG_NAME, "p")
        if len(descWrapper) > 0:
            self.about_us = descWrapper[0].text.strip()
        labels = grid.find_elements(By.TAG_NAME, "dt")
        values = grid.find_elements(By.TAG_NAME, "dd")
        num_attributes = min(len(labels), len(values))
        x_off = 0
        for i in range(num_attributes):
            txt = labels[i].text.strip()
            if txt == 'Website':
                self.website = values[i+x_off].text.strip()
            elif txt == 'Industry':
                self.industry = values[i+x_off].text.strip()
            elif txt == 'Company size':
                self.company_size = values[i+x_off].text.strip()
                if len(values) > len(labels):
                    x_off = 1
            elif txt == 'Headquarters':
                    self.headquarters = values[i+x_off].text.strip()
            elif txt == 'Type':
                self.company_type = values[i+x_off].text.strip()
            elif txt == 'Founded':
                self.founded = values[i+x_off].text.strip()
            elif txt == 'Specialties':
                self.specialties = "\n".join(values[i+x_off].text.strip().split(", "))

        # Don't get the employees, if the company is not a casino
        if self.industry != "Gambling Facilities and Casinos":
            return

        if get_employees:
            self.employees = self.get_employees()

        driver.get(self.linkedin_url)

        if close_on_complete:
            driver.close()

    def get_employees(self, wait_time=10):
        total = []
        list_css = "list-style-none"
        loader = "artdeco-loader"
        next_xpath = '//button[@aria-label="Next"]'
        driver = self.driver

        try:
            see_all_employees = driver.find_element(By.XPATH, '//a[@data-control-name="topcard_see_all_employees"]')
        except:
            pass
        driver.get(os.path.join(self.linkedin_url, "people"))

        _ = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.XPATH, '//span[@dir="ltr"]')))

        driver.execute_script("window.scrollTo(0, Math.ceil(document.body.scrollHeight/2));")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, Math.ceil(document.body.scrollHeight*3/4));")
        time.sleep(1)

        results_list = driver.find_element(By.CSS_SELECTOR, f'.scaffold-finite-scroll__content > .{list_css}')
        results_li = results_list.find_elements(By.TAG_NAME, "li")
        for res in results_li:
            total.append(self.__parse_employee__(res))

        def is_loaded(previous_results):
            loop = 0
            driver.execute_script("window.scrollTo(0, Math.ceil(document.body.scrollHeight));")
            results_li = results_list.find_elements(By.TAG_NAME, "li")
            while len(results_li) == previous_results and loop <= 5:
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, Math.ceil(document.body.scrollHeight));")
                results_li = results_list.find_elements(By.TAG_NAME, "li")
                loop += 1
            return loop <= 5

        def get_data(previous_results):
            results_li = results_list.find_elements(By.TAG_NAME, "li")
            for res in results_li[previous_results:]:
                total.append(self.__parse_employee__(res))

        results_li_len = len(results_li)
        while is_loaded(results_li_len):
            try:
                driver.find_element(By.XPATH, next_xpath).click()
            except:
                pass
            _ = WebDriverWait(driver, wait_time).until(EC.presence_of_element_located((By.CLASS_NAME, list_css)))

            driver.execute_script("window.scrollTo(0, Math.ceil(document.body.scrollHeight/2));")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, Math.ceil(document.body.scrollHeight));")
            try:
                load_more = driver.find_element_by_class_name(loader)
                timeOfLoader = time.time()
                while load_more != None:
                    try:
                        timeSinceLoader = round((time.time() - timeOfLoader), 2)
                        if timeSinceLoader > wait_time:
                            break
                        load_more = driver.find_element_by_class_name(loader)
                    except:
                        load_more = None
                        pass
            except:
                pass

            get_data(results_li_len)
            results_li_len = len(total)
        return total

def get_linkedin_company_link(casino_link, headless_mode):
    """
    Get the company linkedin url via doing a DuckDuckgo search
    """
    Query = f"{casino_link} company profile site:linkedin.com/"
    options = Options()
    if headless_mode:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    driver.get(f"https://duckduckgo.com/?va=j&t=hc&q={Query}")

    pageSource = driver.page_source
    time.sleep(3)
    driver.quit()
    if 'Make sure all words are spelled correctly.' in pageSource:
        return

    urls = list(re.findall('</a></span><a href="(.*?)"', pageSource))
    for url in urls:
        # ensures only the company profile link is gotten
        if "/company" in url and  not "/jobs" in url and not "/people" in url:
            return url
    return
