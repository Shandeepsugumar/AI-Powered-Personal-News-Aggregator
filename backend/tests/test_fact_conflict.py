import os
from ai_agent.ai_service import merge_summaries

def run_test():
    # Ensure you have a valid Groq API key set for this test
    # e.g., export GROQ_API_KEY="your_api_key"
    
    cluster = [
        {
            "source_name": "AppleInsider",
            "source_url": "https://appleinsider.example.com/iphone-18",
            "headline": "iPhone 18 to launch at $899 next September",
            "summary": "Leaks indicate the iPhone 18 will start at $899. It will feature a new M-series chip and launch in September next year."
        },
        {
            "source_name": "MacRumors",
            "source_url": "https://macrumors.example.com/iphone-18-price",
            "headline": "Expect the iPhone 18 to start at $999",
            "summary": "Supply chain rumors point to a price hike for the iPhone 18, starting at $999. It will arrive in September and feature a new M-series chip."
        }
    ]
    
    print("Running Fact-Conflict Test for Model 2...")
    print("-----------------------------------------")
    print("Input cluster has two sources agreeing on September launch and M-series chip, but disagreeing on price ($899 vs $999).\n")
    
    result = merge_summaries(cluster)
    
    print("Model 2 Output:")
    print("--------------")
    print(result)
    print("--------------")
    print("Verify that the output explicitly attributes the conflicting price facts to AppleInsider and MacRumors, rather than picking one.")

if __name__ == "__main__":
    run_test()
