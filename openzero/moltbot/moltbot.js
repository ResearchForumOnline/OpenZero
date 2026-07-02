const express = require('express');
const puppeteer = require('puppeteer');
const app = express();
app.use(express.json());

let browser;
let page;
let lastNavigation = null;
let lastError = null;

async function launchBrowser() {
    console.log(">>> LAUNCHING HEADLESS CHROME...");
    try {
        browser = await puppeteer.launch({
            headless: "new", // MUST be headless on Linux servers
            executablePath: '/usr/bin/google-chrome-stable', // Force use of installed Chrome
args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-dev-shm-usage',
                '--single-process' // Saves RAM
            ]
        });
        page = await browser.newPage();
        // Set a real user agent so websites don't block us immediately
        await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
        console.log(">>> BROWSER IS OPEN AND READY (HEADLESS MODE).");
        lastError = null;
    } catch (err) {
        console.error("!!! FAILED TO LAUNCH BROWSER !!!");
        console.error(err);
        lastError = err.message || String(err);
    }
}

// Launch immediately on start
launchBrowser();

app.get('/status', async (req, res) => {
    const connected = !!(browser && browser.isConnected && browser.isConnected());
    res.json({
        status: connected ? "ready" : "error",
        browser_connected: connected,
        page_open: !!(page && !page.isClosed()),
        last_navigation: lastNavigation,
        last_error: lastError
    });
});

app.post('/goto', async (req, res) => {
    // If browser isn't ready, fail fast
    if (!browser) {
        return res.status(503).json({ status: "error", content: "Browser not initialized yet." });
    }

    let { url } = req.body;
    if (url && !/^https?:\/\//i.test(url)) {
        url = 'https://' + url;
    }
    try {
        console.log("NAVIGATING TO:", url);
        
        // If browser crashed or disconnected, try to restart
        if (!browser.isConnected()) {
            console.log("Browser disconnected. Restarting...");
            await launchBrowser();
        }

        // Reuse page if exists, otherwise make new one
        if (!page || page.isClosed()) {
             page = await browser.newPage();
        }

        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
        lastNavigation = { url, at: new Date().toISOString() };
        lastError = null;
        
        // Take Screenshot for Dashboard (saved to static folder)
        try {
            await page.screenshot({ path: '../static/vision.png' });
        } catch (e) {
            console.log("Screenshot failed (non-fatal): " + e.message);
        }
        
        // Get Text
        const text = await page.evaluate(() => document.body.innerText || "NO TEXT");
        const cleanText = text.replace(/\s+/g, ' ').substring(0, 5000);
        
        res.json({ status: "success", content: cleanText, screenshot: "static/vision.png" });
    } catch (e) {
        console.error("ERROR navigating:", e.message);
        lastError = e.message || String(e);
        res.json({ status: "error", content: e.message });
    }
});

app.listen(3000, '0.0.0.0', () => console.log(">>> MOLTBOT LISTENING ON PORT 3000"));
