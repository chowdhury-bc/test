from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import csv

# Example 1: Basic Web Crawling
def basic_crawl_example():
    """Simple example - crawl Google search results"""
    
    # Setup Chrome driver
    driver = webdriver.Chrome()
    
    try:
        # Navigate to Google
        driver.get("https://www.google.com")
        
        # Find search box and search for something
        search_box = driver.find_element(By.NAME, "q")
        search_box.send_keys("web scraping python")
        search_box.submit()
        
        # Wait for results to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "search"))
        )
        
        # Get search result titles
        results = driver.find_elements(By.CSS_SELECTOR, "h3")
        
        print("Search Results:")
        for i, result in enumerate(results[:5], 1):
            print(f"{i}. {result.text}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

# Example 2: Crawl E-commerce Site (Quotes to Scrape)
def crawl_quotes_site():
    """Crawl quotes from quotes.toscrape.com"""
    
    driver = webdriver.Chrome()
    
    try:
        driver.get("http://quotes.toscrape.com")
        
        quotes_data = []
        
        # Get all quotes from first page
        quotes = driver.find_elements(By.CLASS_NAME, "quote")
        
        for quote in quotes:
            text = quote.find_element(By.CLASS_NAME, "text").text
            author = quote.find_element(By.CLASS_NAME, "author").text
            tags = [tag.text for tag in quote.find_elements(By.CLASS_NAME, "tag")]
            
            quotes_data.append({
                'text': text,
                'author': author,
                'tags': ', '.join(tags)
            })
        
        # Print results
        for i, quote in enumerate(quotes_data, 1):
            print(f"\nQuote {i}:")
            print(f"Text: {quote['text']}")
            print(f"Author: {quote['author']}")
            print(f"Tags: {quote['tags']}")
            
        return quotes_data
        
    except Exception as e:
        print(f"Error: {e}")
        return []
    finally:
        driver.quit()

# Example 3: Multi-page Crawling
def crawl_multiple_pages():
    """Crawl multiple pages of quotes"""
    
    options = Options()
    options.add_argument("--headless")  # Run in background
    driver = webdriver.Chrome(options=options)
    
    all_quotes = []
    
    try:
        for page in range(1, 4):  # Crawl first 3 pages
            url = f"http://quotes.toscrape.com/page/{page}/"
            driver.get(url)
            
            print(f"Crawling page {page}...")
            
            quotes = driver.find_elements(By.CLASS_NAME, "quote")
            
            for quote in quotes:
                text = quote.find_element(By.CLASS_NAME, "text").text
                author = quote.find_element(By.CLASS_NAME, "author").text
                
                all_quotes.append({
                    'page': page,
                    'text': text,
                    'author': author
                })
            
            # Be respectful - add delay between requests
            time.sleep(1)
        
        print(f"\nTotal quotes collected: {len(all_quotes)}")
        return all_quotes
        
    except Exception as e:
        print(f"Error: {e}")
        return []
    finally:
        driver.quit()

# Example 4: Handle JavaScript/Dynamic Content
def crawl_dynamic_content():
    """Crawl site with JavaScript-loaded content"""
    
    driver = webdriver.Chrome()
    
    try:
        driver.get("http://quotes.toscrape.com/js/")
        
        # Wait for JavaScript to load content
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "quote"))
        )
        
        quotes = driver.find_elements(By.CLASS_NAME, "quote")
        
        print("Quotes from JavaScript-rendered page:")
        for i, quote in enumerate(quotes[:3], 1):
            text = quote.find_element(By.CLASS_NAME, "text").text
            author = quote.find_element(By.CLASS_NAME, "author").text
            print(f"{i}. {text} - {author}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

# Example 5: Save Data to CSV
def crawl_and_save_csv():
    """Crawl data and save to CSV file"""
    
    driver = webdriver.Chrome()
    
    try:
        driver.get("http://quotes.toscrape.com")
        
        quotes = driver.find_elements(By.CLASS_NAME, "quote")
        
        # Save to CSV
        with open('quotes.csv', 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Text', 'Author', 'Tags'])  # Header
            
            for quote in quotes:
                text = quote.find_element(By.CLASS_NAME, "text").text
                author = quote.find_element(By.CLASS_NAME, "author").text
                tags = [tag.text for tag in quote.find_elements(By.CLASS_NAME, "tag")]
                
                writer.writerow([text, author, ', '.join(tags)])
        
        print("Data saved to quotes.csv")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

# Example 6: Advanced Crawling with Error Handling
def advanced_crawl_example():
    """Advanced crawling with better error handling and options"""
    
    # Configure Chrome options
    options = Options()
    options.add_argument("--headless")  # Run without GUI
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get("http://quotes.toscrape.com")
        
        # Scroll to load more content if needed
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        quotes = driver.find_elements(By.CLASS_NAME, "quote")
        
        crawled_data = []
        
        for quote in quotes:
            try:
                text = quote.find_element(By.CLASS_NAME, "text").text
                author = quote.find_element(By.CLASS_NAME, "author").text
                tags = [tag.text for tag in quote.find_elements(By.CLASS_NAME, "tag")]
                
                crawled_data.append({
                    'text': text.strip('"'),
                    'author': author,
                    'tags': tags,
                    'tag_count': len(tags)
                })
                
            except Exception as e:
                print(f"Error processing quote: {e}")
                continue
        
        print(f"Successfully crawled {len(crawled_data)} quotes")
        return crawled_data
        
    except Exception as e:
        print(f"Main error: {e}")
        return []
    finally:
        driver.quit()

# Run examples
if __name__ == "__main__":
    print("=== Example 1: Basic Crawling ===")
    basic_crawl_example()
    
    print("\n=== Example 2: Crawl Quotes Site ===")
    crawl_quotes_site()
    
    print("\n=== Example 3: Multi-page Crawling ===")
    crawl_multiple_pages()
    
    print("\n=== Example 4: Dynamic Content ===")
    crawl_dynamic_content()
    
    print("\n=== Example 5: Save to CSV ===")
    crawl_and_save_csv()
    
    print("\n=== Example 6: Advanced Crawling ===")
    advanced_crawl_example()
