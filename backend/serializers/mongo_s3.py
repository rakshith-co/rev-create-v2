from datetime import datetime, timezone
import logging

from repos import creatives as creatives_repo
from core.protocols import OutputSerializer, PipelineInputs, AdCopy
from services.creative_registry import CreativeSubtype, CreativeSource, get_size_specs, CreativeType
from services.s3 import upload_bytes

logger = logging.getLogger("revCreate.serializers.mongo_s3")

class MongoS3Serializer(OutputSerializer):
    async def write_creative(
        self,
        creative_id: str,
        inputs: PipelineInputs,
        ad_copy: AdCopy | None,
        prompt_used: str,
        variation_index: int,
        subtype: CreativeSubtype,
    ) -> None:
        size_specs = get_size_specs(subtype)
        now = datetime.now(timezone.utc)

        # Build the document
        doc = {
            "_id": creative_id,
            "source": CreativeSource.GENERATED,
            "client_id": inputs.client_id,
            "name": inputs.name,
            "associations": inputs.associations,
            "status": "processing",
            "s3_key": f"creatives/{creative_id}.png",
            "metadata": {
                "type": CreativeType.IMAGE,
                "subtype": subtype,
                "size_specs": size_specs.model_dump(),
            },
            "generated": {
                "prompt_used": prompt_used,
                "variation_index": variation_index,
                "version": 1,
                "parent_id": None,
                "edit_instruction": inputs.edit_instruction,
            },
            "input_sources": {
                "product_images": inputs.product_image_keys,
                "ref_images": inputs.ref_image_keys,
                "logo_images": inputs.logo_image_keys,
            },
            "generation_inputs": {
                "product_name": inputs.product_name,
                "description": inputs.description,
                "persona_info": inputs.persona_info,
                "creative_strategy": inputs.creative_strategy,
                "rera_number": inputs.rera_number,
                "qr_s3_key": inputs.qr_s3_key,
            },
            "ad_copy": ad_copy.model_dump() if ad_copy else None,
            "created_at": now,
        }

        # Handle size variants: they have a platform
        if inputs.size_variant_platform:
            doc["metadata"]["platform"] = inputs.size_variant_platform
            
            # Find the size label if we have size variants specified
            for label, dims, ar in inputs.size_variant_sizes:
                if dims == f"{size_specs.width}x{size_specs.height}":
                    doc["metadata"]["size_label"] = label
                    break
                    
            doc["name"] = f"{inputs.name} ({doc['metadata'].get('size_label', subtype)})"

        # Handle edit / regenerate history
        if inputs.edit_instruction or inputs.parent_s3_key or inputs.parent_creative_s3_key:
            # We are in an edit, regenerate or size_variant mode
            # In these modes, the deserializer should pass the pre-existing document's version and parent_id
            pass # The Pipeline state machine or deserializer would set this up.
            # For simplicity, if we need to update an existing doc, we use upsert or update.
            
        # Preserve fields the router writes into pre-created docs.
        # $setOnInsert is a no-op when the doc already exists, so the router's
        # descriptive name and generated metadata are never overwritten.
        generated = doc.pop("generated", None)
        name = doc.pop("name", None)
        update: dict = {"$set": doc}
        on_insert: dict = {}
        if generated is not None:
            on_insert["generated"] = generated
        if name is not None:
            on_insert["name"] = name
        if on_insert:
            update["$setOnInsert"] = on_insert
        await creatives_repo.upsert(creative_id, update)

    async def upload_image(self, creative_id: str, image_bytes: bytes) -> str:
        s3_key = f"creatives/{creative_id}.png"
        await upload_bytes(s3_key, image_bytes)
        return s3_key

    async def mark_done(self, creative_id: str) -> None:
        await creatives_repo.update(
            creative_id,
            {"status": "done"},
        )

    async def mark_failed(self, creative_id: str, error: str) -> None:
        await creatives_repo.update(
            creative_id,
            {
                "status": "failed",
                "error_message": error
            },
        )
