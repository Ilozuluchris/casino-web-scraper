#Casino web scarper
Gets data from casinos via web scraping. Casinos are gotten from casino aggregators<br> <br>
The data gotten, if present:
- Name
- Website
- Email
- Phone number 
- Skype link
- Telegram link
- Linkedin
    - Name
    - Employees
        - Name
        - Designation
        - Profile_url
        


## Set up
- This project uses python 3.10
- Copy `.env.sample` to `.env` and fill in the right variables 
- Install the dependencies via pipenv or via the requirements.txt
- Run `casino_scraper.py` to scrape the casino sites 
- View data saved in `data.xlsx`