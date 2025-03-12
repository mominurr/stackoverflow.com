import time
import pandas as pd
import requests
from requests_html import HTML
import sys,threading,json,random
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm  # For showing a progress bar
# Global progress bar and lock
pbar = None
pbar_lock = threading.Lock()
HEADERS = {
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
}
user_agents = None
# Load JSON data from a file
with open("user_agents.json", "r", encoding="utf-8") as file:
    user_agents = json.load(file)

def clean_scraped_data(text, keyname=None):
    try:
        if keyname == "votes":
            return text.replace("\nvotes", "")
        elif keyname == "tags":
            return text.replace("\n", ", ")
        elif keyname == "summary":
            return text
    except:
        pass
    return text


def parse_tagged_page(html):
    
    key_names = ["question", "summary", "answers", "votes", "tags", "links"]
    classes_needed = [".s-link", ".s-post-summary--content-excerpt", ".s-post-summary--stats-item.has-answers", ".s-post-summary--stats-item-number", ".tags" ]
    datas = []

    try:
        question_summaries = html.find(".s-post-summary")
        for q_el in question_summaries:
            question_data = {}
            for i, cls in enumerate(classes_needed):
                keyname = key_names[i]
                question_summary_id = q_el.attrs["id"].split("-")[2]
                sub_el = q_el.find(cls, first=True)
                if keyname == "answers":
                    if sub_el is None:
                        question_data["answers"] = 0
                    else:
                        a_sub_el = sub_el.find(".s-post-summary--stats-item-number", first=True)
                        question_data["answers"] = a_sub_el.text
                else:
                    question_data[keyname] = clean_scraped_data(sub_el.text, keyname=keyname)
                    question_data["links"] = f"https://stackoverflow.com/questions/{question_summary_id}"
            datas.append(question_data)
    except:
        pass

    return datas


def extract_data_from_url(url):
    global HEADERS,user_agents
    headers = HEADERS.copy()
    
    retry=0
    while retry<3:
        headers["user-agent"] = random.choice(user_agents)
        try:
            r = requests.get(url,headers=HEADERS,timeout=(10,10))
            # print("status code: ",r.status_code)
            if r.status_code not in range(200, 299):
                retry+=1
                continue
            html = HTML(html=r.text)
            datas = parse_tagged_page(html)

            return datas
        except:
            retry+=1
            pass

    return []


def scrape_stack(start_page=1, end_page=2, pagesize="50", sortby="votes"):
    global pbar_lock,pbar
    base_url = "https://stackoverflow.com/questions"
    all_page_data = []
    # iterating through each pages
    for i in range(start_page, end_page):
        url = f"{base_url}?tab={sortby}&page={i}&pagesize={pagesize}"
        data_list = extract_data_from_url(url)
        # print(f"Page: {i} | {len(data_list)} questions collected")
        if data_list and len(data_list)!=0:
            all_page_data.extend(data_list)
        time.sleep(1)
        
        # Update progress bar in a thread-safe way
        with pbar_lock:
            pbar.update(1)  # Update progress bar after each page
    
    return all_page_data



def main(file_name="data",number_of_threads=20, max_page=1, pagesize="50", sortby="votes"):
    full_pages_data = []
    # create start_page,end_page number from total 20k pages number in 20 slots
    # Calculate the number of pages per slot
    pages_per_thread = max_page // number_of_threads

    # Create start and end page numbers for each slot
    page_ranges = []

    for i in range(number_of_threads):
        start_page = i * pages_per_thread + 1
        # Ensure the last slot includes all remaining pages
        end_page = (i + 1) * pages_per_thread if i < number_of_threads - 1 else max_page
        page_ranges.append((start_page, end_page, pagesize, sortby))

    display_ranges= []
    # Display the page ranges
    for i, (start, end, pagesize, sortby) in enumerate(page_ranges, 1):
        display_ranges.append({"Number of thread": i,"Start Page":start, "End Page": end, "pageSize":pagesize, "sortBy":sortby})
    display_df = pd.DataFrame(display_ranges)
    print(display_df.head(5),"\n")

    # Using ThreadPoolExecutor to handle the threading
    completed_threads = 0  # To keep track of how many threads have finished
    with ThreadPoolExecutor(max_workers=number_of_threads) as executor:
        global pbar  # Declare pbar as global so it can be updated in scrape_stack
        with tqdm(total=max_page, desc="Progress") as pbar:
            future_to_range = {executor.submit(scrape_stack, *page_range): page_range for page_range in page_ranges}
            
            # Wait for all threads to complete
            for future in as_completed(future_to_range):
                page_data = future.result()  # Collect the data from each completed thread
                if page_data and len(page_data) != 0:
                    full_pages_data.extend(page_data)
                completed_threads += 1
                # print(f"✅ Thread {completed_threads}/{number_of_threads} completed")
                with open("thread_status.log","a+",encoding="utf-8") as f:
                    f.write(f"✅ Thread {completed_threads}/{number_of_threads} completed\n")

    # Save the data to CSV
    df = pd.DataFrame(full_pages_data)
    df.to_csv(f"../data/{file_name}.csv", index=False)
    print(f"\n✅ Total questions collected: {len(full_pages_data)}")


if __name__ == '__main__':
    file_name = "raw_data_of_stackoverflow"
    main(file_name=file_name, number_of_threads=20, max_page=20000, pagesize="50", sortby="votes")

    