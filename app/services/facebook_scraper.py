import json
import time
import requests
from playwright.async_api import async_playwright
from urllib.parse import parse_qs, urlparse, unquote
from dotenv import load_dotenv
import os
import asyncio
from app.utils.utils import (
    deep_get, parse_content, clean_graphql_response, parse_graphql_comment_replies,
    parse_facebook_post, extract_post_id_from_html, encode_feedback_id,
    parse_html_for_params, save_to_excel
)

load_dotenv()

async def scrape_page(urls, proxy):
    """Scrape URLs, extract HTML and GraphQL parameters using Async Playwright."""
    if isinstance(urls, str):
        urls = [urls]

    cookies = [
        {"name": "datr", "value": "l1UCaAbX2BLP2Pq7J7_tjETO", "domain": ".facebook.com", "path": "/", "expires": 1779543472, "httpOnly": True, "secure": True},
        {"name": "sb", "value": "l1UCaEBMktmKJNccbMAPQSH3", "domain": ".facebook.com", "path": "/", "expires": 1779543472, "httpOnly": True, "secure": True},
    ]

    required_params = {"x-fb-lsd", "lsd", "jazoest", "__rev", "__spin_r", "__hs", "__hsi", "__csr", "dpr"}
    collected_params = {}
    html_content = None
    network_params = {}
    captured_cookies = []

    async with async_playwright() as p:
        # Prepare browser launch arguments
        browser_args = {
            "headless": True,
            "args": [
                "--disable-extensions",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--disable-sync",
                "--disable-translate",
            ]
        }

        # Add proxy if credentials are provided and valid
        use_proxy = proxy.get("username") and proxy.get("password")
        if use_proxy:
            browser_args["proxy"] = {
                "server": "isp.smartproxy.com:10000",
                "username": proxy["username"],
                "password": proxy["password"],
            }

        try:
            browser = await p.chromium.launch(**browser_args)
        except Exception as e:
            print(f"Failed to launch browser with proxy: {str(e)}. Falling back to local IP.")
            browser_args.pop("proxy", None)  # Remove proxy config
            browser = await p.chromium.launch(**browser_args)

        if not use_proxy:
            print("Warning: No proxy credentials provided. Using local IP address.")

        context = await browser.new_context(
            no_viewport=True,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
            bypass_csp=True,
            java_script_enabled=True
        )
        await context.clear_cookies()
        await context.add_cookies(cookies)

        for url in urls:
            page = await context.new_page()

            async def handle_route(route):
                request = route.request
                # Block media requests
                if any(request.url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".mp4", ".webm"]):
                    await route.abort()
                    return

                # Handle GraphQL requests
                if "/api/graphql/" in request.url.lower():
                    headers = request.headers
                    parsed_url = urlparse(request.url)
                    query_params = parse_qs(parsed_url.query)
                    params = {key: unquote(value[0]) if value else "" for key, value in query_params.items()}
                    try:
                        post_data = request.post_data
                        if post_data:
                            for param in post_data.split("&"):
                                if "=" in param:
                                    key, value = param.split("=", 1)
                                    params[unquote(key)] = unquote(value)
                    except Exception:
                        pass

                    network_params.update({
                        "x-fb-lsd": headers.get("x-fb-lsd", network_params.get("x-fb-lsd", "")),
                        "lsd": params.get("lsd", network_params.get("lsd", "")),
                        "jazoest": params.get("jazoest", network_params.get("jazoest", "")),
                        "__rev": params.get("__rev", network_params.get("__rev", "")),
                        "__spin_r": params.get("__spin_r", network_params.get("__spin_r", "")),
                        "__hs": params.get("__hs", network_params.get("__hs", "")),
                        "__hsi": params.get("__hsi", network_params.get("__hsi", "")),
                        "__csr": params.get("__csr", network_params.get("__csr", "")),
                        "dpr": params.get("dpr", network_params.get("dpr", "2")),
                    })

                await route.continue_()

            await page.route("**/*", handle_route)

            try:
                await page.goto(url, timeout=20000)
                await page.wait_for_load_state("networkidle", timeout=20000)

                html_content = await page.content()
                captured_cookies = await context.cookies()

                post_id = extract_post_id_from_html(html_content)
                feedback_id = encode_feedback_id(post_id)
                collected_params["post_id"] = post_id
                collected_params["feedback_id"] = feedback_id
                collected_params.update(network_params)

                missing_params = [param for param in required_params if param not in collected_params or not collected_params[param]]
                if missing_params:
                    collected_params.update(await parse_html_for_params(html_content, missing_params))

                collected_params.update({
                    "av": "0",
                    "__user": "0",
                    "__a": "1",
                    "fb_api_caller_class": "RelayModern",
                    "fb_api_req_friendly_name": "CommentsListComponentsPaginationQuery",
                    "server_timestamps": "true",
                    "doc_id": "9445061768946657",
                    "variables": json.dumps({
                        "commentsAfterCount": -1,
                        "commentsAfterCursor": None,
                        "commentsBeforeCount": None,
                        "commentsBeforeCursor": None,
                        "commentsIntentToken": None,
                        "feedLocation": "PERMALINK",
                        "focusCommentID": None,
                        "scale": 4,
                        "useDefaultActor": False,
                        "id": feedback_id,
                        "__relay_internal__pv__IsWorkUserrelayprovider": False
                    })
                })

            except Exception as e:
                print(f"Error scraping page {url}: {str(e)}")
            finally:
                await page.close()

        await browser.close()

    return collected_params, html_content, captured_cookies

def make_graphql_request(params, cookies, url, request_type="comments", cursor=None, feedback_id=None, all_comments=None, depth=0, max_depth=10, max_retries=2):
    """
    Unified function to make GraphQL requests for comments or replies.
    
    Args:
        params (dict): GraphQL request parameters (e.g., lsd, jazoest).
        cookies (list): List of cookie dictionaries.
        url (str): Referer URL for the request.
        request_type (str): 'comments' or 'replies' to determine the type of data to fetch.
        cursor (str, optional): Pagination cursor (end_cursor for comments, expansion_token for replies).
        feedback_id (str, optional): Feedback ID for replies.
        all_comments (list, optional): Accumulated comments for recursive comment fetching.
        depth (int): Current recursion depth for comments.
        max_depth (int): Maximum recursion depth for comments.
        max_retries (int): Maximum number of retry attempts for failed requests.
    
    Returns:
        dict or list: For comments, returns a list of all comments; for replies, returns parsed reply data.
    """
    if request_type not in ["comments", "replies"]:
        raise ValueError(f"Invalid request_type: {request_type}")

    if all_comments is None and request_type == "comments":
        all_comments = []

    if request_type == "comments" and depth >= max_depth:
        print(f"Reached max depth {max_depth}, stopping recursion")
        return all_comments

    graphql_url = "https://www.facebook.com/api/graphql/"

    # Common headers
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.facebook.com",
        "Referer": url,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "X-ASBD-ID": params.get("x-asbd-id", ""),
        "X-FB-LSD": params.get("lsd", ""),
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Connection": "keep-alive",
        "DNT": "1",
        "Sec-GPC": "1",
        "TE": "trailers",
    }

    # Common payload fields
    payload = {
        "av": params.get("av", "0"),
        "__user": params.get("__user", "0"),
        "__a": params.get("__a", "1"),
        "lsd": params.get("lsd", ""),
        "jazoest": params.get("jazoest", ""),
        "fb_api_caller_class": "RelayModern",
        "__spin_b": "trunk",
        "__spin_t": str(int(time.time())),
        "server_timestamps": "true",
    }

    # Type-specific configuration
    if request_type == "comments":
        headers["X-FB-Friendly-Name"] = params.get("fb_api_req_friendly_name", "CommentsListComponentsPaginationQuery")
        payload.update({
            "fb_api_req_friendly_name": "CommentsListComponentsPaginationQuery",
            "doc_id": "9445061768946657",
        })
        variables = json.loads(params.get("variables", "{}"))
        variables["commentsAfterCursor"] = cursor
        variables["scale"] = 4
    else:  # replies
        headers["X-FB-Friendly-Name"] = "Depth1CommentsListPaginationQuery"
        payload.update({
            "__aaid": "0",
            "__req": "n",
            "__hs": params.get("__hs", ""),
            "dpr": params.get("dpr", "2"),
            "__ccg": "EXCELLENT",
            "__rev": params.get("__rev", ""),
            "__s": params.get("__s", ""),
            "__hsi": params.get("__hsi", ""),
            "__csr": params.get("__csr", ""),
            "__comet_req": "15",
            "__spin_r": params.get("__spin_r", ""),
            "fb_api_req_friendly_name": "Depth1CommentsListPaginationQuery",
            "doc_id": "9529899550379477",
        })
        variables = {
            "expansionToken": cursor,
            "clientKey": None,
            "feedLocation": "PERMALINK",
            "focusCommentID": None,
            "repliesAfterCount": None,
            "repliesAfterCursor": None,
            "repliesBeforeCount": None,
            "repliesBeforeCursor": None,
            "scale": 2,
            "useDefaultActor": False,
            "id": feedback_id,
            "__relay_internal__pv__IsWorkUserrelayprovider": False
        }

    payload["variables"] = json.dumps(variables)

    cookies_dict = {cookie["name"]: cookie["value"] for cookie in cookies}

    for attempt in range(max_retries):
        try:
            time.sleep(0.5)  # Reduced rate limiting delay
            response = requests.post(graphql_url, headers=headers, data=payload, cookies=cookies_dict)
            response.raise_for_status()

            if request_type == "replies":
                return parse_graphql_comment_replies(response.text, "replies")

            # For comments
            raw_data = response.text
            json_data = parse_content(raw_data)
            if not json_data:
                json_data = clean_graphql_response(raw_data)
                json_data = json.loads(json_data) if json_data else None

            if json_data:
                comments = parse_graphql_comment_replies(json.dumps(json_data), "comments")
                if comments and comments["results"]:
                    for comment in comments["results"]:
                        feedback_id = comment.get("feedback_id")
                        reply_count = comment.get("reply_count", 0)
                        expansion_token = comment.get("expansion_token")
                        if feedback_id and reply_count > 0:
                            reply = make_graphql_request(
                                params, cookies, url, request_type="replies",
                                cursor=expansion_token, feedback_id=feedback_id
                            ).get("results", [])
                            comment["replies"] = reply
                    all_comments.extend(comments["results"])

                page_info = comments.get("page_info", {})
                next_cursor = page_info.get("end_cursor")
                has_next_page = page_info.get("has_next_page", False)

                if has_next_page and next_cursor:
                    return make_graphql_request(
                        params, cookies, url, request_type="comments",
                        cursor=next_cursor, all_comments=all_comments,
                        depth=depth + 1, max_depth=max_depth
                    )

                return all_comments
            else:
                print("No valid JSON data in response")
                return all_comments

        except requests.RequestException as e:
            print(f"Attempt {attempt + 1}/{max_retries} failed for {request_type}: {str(e)}")
            if attempt == max_retries - 1:
                print(f"Failed to fetch {request_type} after {max_retries} attempts")
                return {"results": [], "page_info": {"end_cursor": None, "has_next_page": False}} if request_type == "replies" else all_comments
            time.sleep(2 ** attempt)  # Exponential backoff

async def scrape_facebook_post(url: str):
    """Main function to scrape a Facebook post and its comments."""
    proxy = {
        "username": os.getenv("PROXY_USERNAME"),
        "password": os.getenv("PROXY_PASSWORD")
    }
    params, html_content, cookies = await scrape_page(url, proxy)
    comment_data = []
    comments = make_graphql_request(params, cookies, url, request_type="comments")
    if comments:
        comment_data.append(comments)
    
    parsed_data = parse_content(html_content)
    if not parsed_data:
        print("Failed to parse post content, but continuing with available data")
    
    post_data = parse_facebook_post(parsed_data, comment_data) if parsed_data else {
        "post_id": params.get("post_id", "unknown"),
        "post_url": url,
        "comments": {"total_count": len(comments), "details": comments}
    }
    
    return post_data

if __name__ == "__main__":
    async def main():
        proxy = {
            "username": os.getenv("PROXY_USERNAME"),
            "password": os.getenv("PROXY_PASSWORD")
        }
        urls = ["https://www.facebook.com/Gate7.online/posts/pfbid0kAFpBv4fFPjL7dS4fAdZKLt7Yb46pKBsftg1GThLSsboWq2enfG3TQkcfkgdYPTgl"]
        start_time = time.time()
        
        try:
            params, html_content, cookies = await scrape_page(urls, proxy)
        except Exception as e:
            print(f"Error during scraping: {str(e)}")
            return
        
        comment_data = []
        for url in urls:
            comments = make_graphql_request(params, cookies, url, request_type="comments")
            if comments:
                comment_data.append(comments)
        
        parsed_data = parse_content(html_content)
        post_data = parse_facebook_post(parsed_data, comment_data) if parsed_data else {
            "post_id": params.get("post_id", "unknown"),
            "post_url": url,
            "comments": {"total_count": len(comments), "details": comments}
        }
        if post_data:
            filename = f"facebook_post_{post_data['post_id']}.xlsx"
            save_to_excel(post_data, filename)
            print(f"Data saved to {filename}")
        
        print(f"Execution time: {time.time() - start_time} seconds")
    
    asyncio.run(main())