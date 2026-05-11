import httpx
import asyncio
import time
import zipfile
import io
import json
from pathlib import Path
import os
from dotenv import load_dotenv
import fitz  # PyMuPDF

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
            # 遍历每个子列表（每个子列表代表一页）
            for page_idx, sublist in enumerate(content):
                if isinstance(sublist, list):
                    # 遍历页面中的每个元素
                    for item in sublist:
                        if isinstance(item, dict):
                            # 处理复杂的 content 结构
                            text = ""
                            item_content = item.get("content")
                            item_type = item.get("type")
                            
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
                                # 处理段落类型
                                elif "paragraph_content" in item_content:
                                    paragraph_content = item_content["paragraph_content"]
                                    if isinstance(paragraph_content, list):
                                        for para_item in paragraph_content:
                                            if isinstance(para_item, dict):
                                                para_text = para_item.get("content")
                                                if isinstance(para_text, str):
                                                    text += para_text
                                # 处理表格类型
                                elif "html" in item_content:
                                    # 从 HTML 中提取文本
                                    html = item_content.get("html", "")
                                    # 简单处理：移除 HTML 标签，保留文本
                                    import re
                                    text = re.sub('<[^<]+?>', '', html)
                                    # 清理多余的空白字符
                                    text = ' '.join(text.split())
                                # 处理页眉类型
                                elif "page_header_content" in item_content:
                                    header_content = item_content["page_header_content"]
                                    if isinstance(header_content, list):
                                        for header_item in header_content:
                                            if isinstance(header_item, dict):
                                                header_text = header_item.get("content")
                                                if isinstance(header_text, str):
                                                    text += header_text
                                # 处理页脚类型
                                elif "page_footer_content" in item_content:
                                    footer_content = item_content["page_footer_content"]
                                    if isinstance(footer_content, list):
                                        for footer_item in footer_content:
                                            if isinstance(footer_item, dict):
                                                footer_text = footer_item.get("content")
                                                if isinstance(footer_text, str):
                                                    text += footer_text
                                # 处理其他可能的内容类型
                                elif "text" in item_content:
                                    text = item_content["text"]
                                elif "content" in item_content:
                                    text = item_content["content"]
                            
                            # 确保 text 是字符串类型
                            if isinstance(text, str) and text.strip():
                                paragraphs.append({
                                    "content": text.strip(),
                                    "page_num": page_idx + 1,  # 页面索引从1开始
                                    "bbox": item.get("bbox"),
                                    "type": item_type,  # 保存元素类型
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
        print(f"\n共提取了 {len(paragraphs)} 个段落")
        
        return paragraphs

def highlight_keyword_in_pdf(input_pdf, output_pdf, keyword, paragraphs):
    """
    在 PDF 中将包含关键词的句子改成红色字
    
    参数:
        input_pdf: 输入 PDF 文件路径
        output_pdf: 输出 PDF 文件路径
        keyword: 要高亮的关键词
        paragraphs: 解析出的段落列表
    """
    # 打开 PDF 文件
    doc = fitz.open(input_pdf)
    
    # 遍历每一页
    for page_num in range(len(doc)):
        page = doc[page_num]
        current_page_num = page_num + 1
        print(f"处理第 {current_page_num} 页...")
        
        # 直接在页面中搜索关键词（不依赖于段落提取）
        # 使用更精确的搜索参数
        text_instances = page.search_for(keyword)
        print(f"在第 {current_page_num} 页找到 {len(text_instances)} 个 '{keyword}' 实例")
        
        # 去重处理，避免重复高亮
        unique_instances = []
        for inst in text_instances:
            # 检查是否与已添加的实例重叠
            overlapping = False
            for existing in unique_instances:
                # 检查两个矩形是否重叠
                if inst.intersects(existing):
                    overlapping = True
                    break
            if not overlapping:
                unique_instances.append(inst)
        
        print(f"去重后剩余 {len(unique_instances)} 个实例")
        
        # 为每个找到的文本实例添加红色标注
        for i, inst in enumerate(unique_instances):
            try:
                # 创建高亮标注
                highlight = page.add_highlight_annot(inst)
                # 设置红色高亮，增加透明度
                highlight.set_colors(stroke=[1, 0, 0], fill=[1, 0.8, 0.8])  # 红色边框，浅红色填充
                # 设置线宽和透明度
                highlight.set_border(width=1)
                highlight.update(opacity=0.6)
                print(f"在第 {current_page_num} 页添加了红色高亮 {i+1}/{len(unique_instances)}: {inst}")
            except Exception as e:
                print(f"添加高亮时出错: {e}")
        
        # 检查是否有段落但没有找到关键词
        page_paragraphs = [p for p in paragraphs if p["page_num"] == current_page_num]
        if page_paragraphs and len(text_instances) == 0:
            print(f"第 {current_page_num} 页有 {len(page_paragraphs)} 个段落，但未找到关键词 '{keyword}'")
        elif len(text_instances) > 0:
            print(f"第 {current_page_num} 页处理完成，添加了 {len(unique_instances)} 个高亮标注")
    
    # 保存输出 PDF
    doc.save(output_pdf, garbage=4, deflate=True, clean=True)
    doc.close()
    
    print(f"\n高亮处理完成！")
    print(f"已将包含关键词 '{keyword}' 的句子标记为红色，并保存到 {output_pdf}")
    print("提示：使用 Adobe Acrobat Reader 或其他支持 PDF 标注的查看器查看高亮效果")

async def main():
    # 测试 PDF 文件路径
    pdf_path = "./tutorials/data/1.pdf"
    output_pdf = "./tutorials/data/1_highlighted.pdf"
    keyword = "作业"
    
    if not os.path.exists(pdf_path):
        print(f"PDF 文件不存在: {pdf_path}")
        return
    
    if not MINERU_API_KEY:
        print("请先配置 MINERU_API_KEY 环境变量")
        return
    
    try:
        # 解析 PDF
        paragraphs = await parse_pdf_with_mineru(pdf_path, MINERU_API_KEY)
        
        # 打印前10个段落
        print("\n====== 解析结果 ======")
        for i, p in enumerate(paragraphs[:10]):
            print(f"[{i}] 第{p['page_num']}页: {p['content'][:100]}...")
        
        # 高亮包含关键词的段落
        highlight_keyword_in_pdf(pdf_path, output_pdf, keyword, paragraphs)
        
    except Exception as e:
        print(f"错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())