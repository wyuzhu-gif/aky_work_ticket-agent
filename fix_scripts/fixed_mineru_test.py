import httpx
import asyncio
import time
import zipfile
import io
import json
from pathlib import Path
import os
from dotenv import load_dotenv

# 加载环境变量
dotenv_path = Path("./tutorials/.env")
if dotenv_path.exists():
    load_dotenv(dotenv_path, override=True)
    print(f"加载了配置文件: {dotenv_path}")
else:
    load_dotenv(override=True)
    print("加载了默认配置文件")

MINERU_API_KEY = os.getenv("MINERU_API_KEY")

# 修复后的 extract_paragraphs 函数
def extract_paragraphs(content) -> list[dict]:
    """
    从 MinerU 解析结果中提取段落文本。
    
    MinerU 返回的 JSON 结构可能有多种格式，这个函数会尝试兼容不同格式。
    """
    paragraphs = []
    
    # 情况1：content 是列表
    if isinstance(content, list):
        # 检查列表的第一个元素是否也是列表（content_list_v2.json 的结构）
        if content and isinstance(content[0], list):
            # 遍历每个子列表
            for sublist in content:
                if isinstance(sublist, list):
                    for item in sublist:
                        if isinstance(item, dict):
                            # 处理复杂的 content 结构
                            text = ""
                            item_content = item.get("content")
                            
                            if isinstance(item_content, str):
                                text = item_content
                            elif isinstance(item_content, dict):
                                # 处理标题类型
                                if "title_content" in item_content:
                                    title_content = item_content["title_content"]
                                    if isinstance(title_content, list):
                                        for title_item in title_content:
                                            if isinstance(title_item, dict):
                                                title_text = title_item.get("content")
                                                if isinstance(title_text, str):
                                                    text += title_text
                                # 处理普通文本类型
                                elif "text" in item_content:
                                    text = item_content["text"]
                                elif "content" in item_content:
                                    text = item_content["content"]
                            
                            # 确保 text 是字符串类型
                            if isinstance(text, str) and text.strip():
                                paragraphs.append({
                                    "content": text.strip(),
                                    "page_num": item.get("page_idx", 0) + 1,
                                    "bbox": item.get("bbox"),
                                })
        else:
            # 常规列表结构
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content") or ""
                    # 确保 text 是字符串类型
                    if isinstance(text, dict):
                        # 如果是字典，尝试获取其中的文本内容
                        text = text.get("text") or text.get("content") or ""
                    if isinstance(text, str) and text.strip():
                        paragraphs.append({
                            "content": text.strip(),
                            "page_num": item.get("page_idx", 0) + 1,
                            "bbox": item.get("bbox"),
                        })
        return paragraphs
    
    # 情况2：content 是字典，包含 pages 字段
    if isinstance(content, dict):
        # 情况2.1：包含 pages 字段
        pages = content.get("pages") or []
        for page in pages:
            page_num = page.get("page", 1)
            blocks = page.get("paragraphs") or page.get("blocks") or []
            for block in blocks:
                text = block.get("text") or block.get("content") or ""
                if text.strip():
                    paragraphs.append({
                        "content": text.strip(),
                        "page_num": page_num,
                        "bbox": block.get("bbox"),
                    })
        
        # 情况2.2：包含 pdf_info 字段（MinerU 实际返回的结构）
        pdf_info = content.get("pdf_info") or []
        for page_obj in pdf_info:
            if isinstance(page_obj, dict):
                page_num = int(page_obj.get("page_idx", 0)) + 1
                blocks = page_obj.get("para_blocks") or []
                for block in blocks:
                    if isinstance(block, dict):
                        lines = block.get("lines") or []
                        for line in lines:
                            if isinstance(line, dict):
                                spans = line.get("spans") or []
                                text_parts = []
                                for span in spans:
                                    if isinstance(span, dict):
                                        text = span.get("content") or ""
                                        text_parts.append(text)
                                text = "".join(text_parts)
                                if text.strip():
                                    paragraphs.append({
                                        "content": text.strip(),
                                        "page_num": page_num,
                                        "bbox": line.get("bbox") or block.get("bbox"),
                                    })
    
    return paragraphs

async def parse_pdf_with_mineru(pdf_path: str, api_key: str) -> list[dict]:
    """
    使用 MinerU API 解析 PDF 文档。
    
    参数:
        pdf_path: PDF 文件路径
        api_key: MinerU API 密钥
        
    返回:
        解析后的段落列表
    """
    base_url = "https://mineru.net"
    file_path = Path(pdf_path)
    file_name = file_path.name
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    async with httpx.AsyncClient(timeout=300) as client:
        # 步骤1：请求预签名上传 URL
        print("步骤1：请求上传 URL...")
        resp = await client.post(
            f"{base_url}/api/v4/file-urls/batch",
            headers=headers,
            json={
                "files": [{"name": file_name, "data_id": file_name}],
                "model_version": "vlm",  # 使用视觉语言模型
            }
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        batch_id = data["batch_id"]
        upload_url = data["file_urls"][0]
        print(f"获取到 batch_id: {batch_id}")
        
        # 步骤2：上传 PDF 文件
        print("步骤2：上传 PDF 文件...")
        with open(pdf_path, "rb") as f:
            await client.put(upload_url, content=f.read())
        print("上传完成")
        
        # 步骤3：轮询等待解析完成
        print("步骤3：等待解析完成...")
        max_wait = 300  # 最多等待5分钟
        start_time = time.time()
        
        while True:
            resp = await client.get(
                f"{base_url}/api/v4/extract-results/batch/{batch_id}",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            result = resp.json()["data"]["extract_result"][0]
            
            if result["state"] == "done":
                full_zip_url = result["full_zip_url"]
                print("解析完成")
                break
            elif result["state"] == "failed":
                raise RuntimeError(f"解析失败: {result.get('err_msg')}")
            
            if time.time() - start_time > max_wait:
                raise TimeoutError("解析超时")
            
            await asyncio.sleep(2)  # 每2秒检查一次
        
        # 步骤4：下载并解析结果
        print("步骤4：下载解析结果...")
        resp = await client.get(full_zip_url)
        zip_bytes = resp.content
        
        # 解压并提取 JSON
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            json_files = [n for n in zf.namelist() if n.endswith(".json")]
            if not json_files:
                raise RuntimeError("未找到解析结果")
            
            # 尝试找到 content_list_v2.json 文件
            content_file = None
            for file_name in json_files:
                if "content_list" in file_name:
                    content_file = file_name
                    break
            
            if not content_file:
                content_file = json_files[0]
            
            print(f"使用的 JSON 文件: {content_file}")
            
            with zf.open(content_file) as f:
                content = json.loads(f.read().decode("utf-8"))
        
        print("下载完成")
        
        # 步骤5：提取段落文本
        paragraphs = extract_paragraphs(content)
        print(f"共提取了 {len(paragraphs)} 个段落")
        
        return paragraphs

async def main():
    # 测试 PDF 文件路径
    pdf_path = "./tutorials/data/LangChain v1.1 文档审核类Agent开发实战.pdf"
    
    if not os.path.exists(pdf_path):
        print(f"PDF 文件不存在: {pdf_path}")
        return
    
    if not MINERU_API_KEY:
        print("请先配置 MINERU_API_KEY 环境变量")
        return
    
    try:
        paragraphs = await parse_pdf_with_mineru(pdf_path, MINERU_API_KEY)
        
        # 打印前10个段落
        print("\n====== 解析结果 ======")
        for i, p in enumerate(paragraphs[:10]):
            print(f"[{i}] 第{p['page_num']}页: {p['content'][:100]}...")
            
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())