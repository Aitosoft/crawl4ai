import asyncio
from crawl4ai import AsyncWebCrawler

async def main():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url="https://www.laaketeollisuus.fi/yhteystiedot/yhdistyksen-henkilosto.html")
        print("Scraped Markdown:\n")
        print(result.markdown)

asyncio.run(main())
